import io,json,sqlite3,tempfile,unittest
from pathlib import Path
import engine

class RulesTest(unittest.TestCase):
    def setUp(self): self.db=engine.connect(':memory:')
    def tearDown(self): self.db.close()
    def csv(self,kind,text,asof):return engine.ingest(self.db,text.encode(),'sample.csv',kind,asof)
    def asset(self,serial='A1',state='In stock',assigned='',billed='False'):
        return f'serial_number,model,install_status,assigned_to,assigned,u_billed,po_number,purchase_line.purchase_order.number,purchase_line.purchase_order.ship_to,purchase_line.received,cost\n{serial},Laptop,{state},,{assigned},{billed},123,PO1,Stockroom,2026-07-01,100\n'
    def test_duplicate_import_does_not_add_records(self):
        a=self.csv('inventory',self.asset(),'2026-08-01');b=self.csv('inventory',self.asset(),'2026-08-01')
        self.assertFalse(a['duplicate']);self.assertTrue(b['duplicate']);self.assertEqual(len(engine.imports(self.db)),1)
    def test_invalid_format_leaves_no_import(self):
        with self.assertRaises(ValueError):self.csv('inventory','serial,model\nA,Laptop\n','2026-08-01')
        self.assertEqual(len(engine.imports(self.db)),0)
    def test_stock_movements_ignore_net_replenishment(self):
        self.csv('inventory',self.asset(),'2026-08-01')
        self.csv('inventory',self.asset(state='In use',assigned='2026-08-15')+self.asset('A2').split('\n',1)[1],'2026-09-01')
        s=engine.build(self.db);self.assertEqual(s['stats']['stock'],1);self.assertEqual(s['stats']['deployments'],1)
        self.assertEqual(s['stocks'][0]['span_days'],31)
    def test_canceled_and_requested_orders_not_inbound(self):
        self.csv('inventory',self.asset(),'2026-09-01')
        self.csv('bulk_orders','purchase_order,model,ordered_quantity,status,purchase_order.ship_to,expected_delivery\nPO2,Laptop,50,Canceled,Stockroom,2026-09-03\nPO3,Laptop,25,Requested,Stockroom,2026-09-03\nPO4,Laptop,10,Ordered,Stockroom,2026-09-03\n','2026-09-01')
        g=engine.build(self.db)['stocks'][0];self.assertEqual(g['inbound'],10);self.assertEqual(g['timely_inbound'],10)
    def test_missing_eta_excluded_from_timely_supply(self):
        self.csv('inventory',self.asset(),'2026-09-01')
        self.csv('bulk_orders','purchase_order,model,ordered_quantity,status,purchase_order.ship_to,expected_delivery\nPO2,Laptop,10,Ordered,Stockroom,\n','2026-09-01')
        g=engine.build(self.db)['stocks'][0];self.assertEqual(g['inbound'],10);self.assertEqual(g['timely_inbound'],0);self.assertEqual(g['risk'],'Watch')
    def eam(self,which,amount=100):
        import openpyxl
        wb=openpyxl.Workbook();w=wb.active;w.append(['Success Line Details'])
        if which=='error':w.append(['Error Line Details'])
        w.append(['batch',7,None,'123','2026-07-10','REQ1','RITM1','A1','2026-07-01',amount,0,amount,0,amount,amount,'PTA',None,100,None,'User PTA not available.' if which=='error' else None]);buf=io.BytesIO();wb.save(buf);return buf.getvalue()
    def test_rejection_is_not_success_and_disappearance_not_resolution(self):
        self.csv('inventory',self.asset(state='In use',assigned='2026-07-10'),'2026-08-01')
        engine.ingest(self.db,self.eam('error'),'error.xlsx','eam','2026-07-28')
        self.csv('inventory',self.asset(state='In use',assigned='2026-07-10'),'2026-09-01')
        s=engine.build(self.db);self.assertEqual(s['stats']['reject_amount'],100);self.assertEqual(s['issues'][0]['type'],'rejected')
        engine.ingest(self.db,self.eam('success'),'success.xlsx','eam','2026-08-28');self.assertEqual(engine.build(self.db)['stats']['reject_amount'],0)
    def test_manual_input_does_not_resolve_rejection(self):
        self.csv('inventory',self.asset(state='In use',assigned='2026-07-10'),'2026-08-01')
        engine.ingest(self.db,self.eam('error'),'error.xlsx','eam','2026-07-28')
        self.csv('manual','ASSET_NUMBER,TRANSACTION_TYPE,PRICE,QUANTITY,SOURCE_BATCH_NUMBER,SOURCE_TRANSACTION_ID\nA1,CHARGE,100,1,BATCH1,1\n','2026-08-01')
        s=engine.build(self.db);self.assertEqual(s['stats']['reject_amount'],100);self.assertTrue(any(i['type']=='manual' for i in s['issues']))
    def test_missing_serial_is_flagged_and_excluded_from_tracked_assets(self):
        self.csv('inventory',self.asset(serial=''),'2026-08-01')
        s=engine.build(self.db)
        self.assertEqual(s['stats']['assets'],0)
        self.assertEqual(sum(i['type']=='missing_serial' for i in s['issues']),1)
    def test_decision_api_persists_and_requires_resolution_note(self):
        import app
        original_db,original_cache=app.DB,app.CACHE
        try:
            with tempfile.TemporaryDirectory() as td:
                app.DB=Path(td)/'test.sqlite3';app.CACHE=None
                with engine.connect(app.DB) as db:
                    engine.ingest(db,self.asset(state='In use',assigned='2026-07-10').encode(),'inv.csv','inventory','2026-08-01')
                    engine.ingest(db,self.eam('error'),'billing.xlsx','eam','2026-07-28')
                issue=app.state()['issues'][0]
                def post(body):
                    h=app.Handler.__new__(app.Handler);payload=json.dumps(body).encode();h.headers={'Content-Length':str(len(payload))};h.rfile=io.BytesIO(payload);h.path='/api/decision';responses=[];h.response=lambda v,status=200:responses.append((status,v));h.do_POST();return responses[0]
                status,result=post(dict(id=issue['id'],state='Investigating',owner='Test owner',note='Evidence checked'))
                self.assertEqual(status,200,result);app.CACHE=None
                restored=next(i for i in app.state()['issues'] if i['id']==issue['id']);self.assertEqual(restored['state'],'Investigating');self.assertEqual(restored['owner'],'Test owner')
                status,result=post(dict(id=issue['id'],state='Resolved',note=''))
                self.assertEqual(status,400);self.assertIn('disposition',result['error'])
                status,result=post(dict(id=issue['id'],state='Resolved',note='Test disposition'))
                self.assertEqual(status,200,result);app.CACHE=None;self.assertEqual(app.state()['stats']['open_issues'],0)
        finally:app.DB,app.CACHE=original_db,original_cache
if __name__=='__main__':unittest.main()
