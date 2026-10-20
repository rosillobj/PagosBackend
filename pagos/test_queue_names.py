import unittest
from .queue_names import plan_names, apply_names


class QueueNameTests(unittest.TestCase):
    def setUp(self):
        self.client={'id':1,'nombre':'José Pérez','ip_completa':'192.168.1.21'}
        self.queue={'.id':'*1','name':'Nombre viejo','target':'192.168.1.21/32','max-limit':'2M/5M','disabled':True}

    def test_exact_target_and_parent_preserved(self):
        plan=plan_names([self.client],[{'.id':'*0','name':'Padre','target':'192.168.1.0/24'},self.queue])
        self.assertEqual(len(plan['changes']),1)
        self.assertEqual(plan['changes'][0]['new_name'],'José Pérez')

    def test_conflict_duplicate_and_multi_target_are_skipped(self):
        for queues in ([self.queue,self.queue], [self.queue, {'.id':'*2','name':'José Pérez','target':'192.168.1.22'}], [{**self.queue,'target':'192.168.1.21/32,192.168.1.22/32'}]):
            self.assertEqual(plan_names([self.client],queues)['changes'],[])

    def test_only_name_is_written_and_verified(self):
        queue=self.queue.copy(); writes=[]
        def api(command, **kwargs):
            if command.endswith('/print'):return [queue.copy()]
            writes.append(kwargs);queue['name']=kwargs['name'];return []
        changes=plan_names([self.client],[queue])['changes']
        result=apply_names(api,changes,[self.client])
        self.assertEqual(len(result['updated']),1)
        self.assertEqual(writes,[{'.id':'*1','name':'José Pérez'}])
        self.assertEqual(queue['max-limit'],'2M/5M')
        self.assertTrue(queue['disabled'])

    def test_changed_client_or_queue_is_not_updated(self):
        changes=plan_names([self.client],[self.queue])['changes']
        def api(command, **kwargs):
            self.assertTrue(command.endswith('/print'))
            return [{**self.queue,'name':'Cambio manual'}]
        result=apply_names(api,changes,[self.client])
        self.assertEqual(result['updated'],[])
        self.assertEqual(len(result['skipped']),1)

    def test_second_run_has_no_pending_changes(self):
        self.assertEqual(plan_names([self.client],[{**self.queue,'name':self.client['nombre']}])['changes'],[])

    def test_write_failure_stops_subsequent_writes(self):
        clients=[self.client,{'id':2,'nombre':'Otra','ip_completa':'192.168.1.22'}]
        queues=[self.queue,{'.id':'*2','name':'Anterior','target':'192.168.1.22/32'}]
        writes=[]
        def api(command, **kwargs):
            if command.endswith('/print'):return queues
            writes.append(kwargs);raise RuntimeError('permission denied')
        result=apply_names(api,plan_names(clients,queues)['changes'],clients)
        self.assertEqual(len(writes),1)
        self.assertEqual(len(result['failed']),1)
        self.assertEqual(len(result['skipped']),1)
