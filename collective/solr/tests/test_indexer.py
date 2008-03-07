from unittest import TestCase, TestSuite, makeSuite, main
from threading import Thread
from DateTime import DateTime

from collective.solr.indexer import SolrIndexQueueProcessor
from collective.solr.tests.test_solr import fakehttp
from collective.solr.tests.utils import getData
from collective.solr.solr import SolrConnection


class Foo:
    """ dummy test object """
    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class QueueIndexerTests(TestCase):

    def setUp(self):
        self.proc = SolrIndexQueueProcessor()
        self.proc.setHost()
        conn = self.proc.getConnection()
        fakehttp(conn, getData('schema.xml'), [])   # fake schema response
        self.proc.getSchema()                       # read and cache the schema

    def tearDown(self):
        self.proc.closeConnection()

    def testPrepareData(self):
        data = {'allowedRolesAndUsers': ['user:test_user_1_', 'user:portal_owner']}
        SolrIndexQueueProcessor().prepareData(data)
        self.assertEqual(data, {'allowedRolesAndUsers': ['user$test_user_1_', 'user$portal_owner']})

    def testIndexObject(self):
        proc = self.proc
        output = []
        response = getData('add_response.txt')
        fakehttp(proc.getConnection(), response, output)    # fake add response
        proc.index(Foo(id='500', name='python test doc'))   # indexing sends data
        output = ''.join(output).replace('\r', '')
        self.assertEqual(output, getData('add_request.txt'))

    def testPartialIndexObject(self):
        proc = self.proc
        foo = Foo(id='500', name='foo', price=42.0)
        # first index all attributes...
        output = []
        response = getData('add_response.txt')
        fakehttp(proc.getConnection(), response, output)
        proc.index(foo)
        output = ''.join(output).replace('\r', '')
        self.assert_(output.find('<field name="price">42.0</field>') > 0, '"price" data not found')
        # then only a subset...
        output = []
        response = getData('add_response.txt')
        fakehttp(proc.getConnection(), response, output)
        proc.index(foo, attributes=['id', 'name'])
        output = ''.join(output).replace('\r', '')
        self.assert_(output.find('<field name="name">foo</field>') > 0, '"name" data not found')
        self.assertEqual(output.find('price'), -1, '"price" data found?')
        self.assertEqual(output.find('42'), -1, '"price" data found?')

    def testDateIndexing(self):
        proc = self.proc
        foo = Foo(id='zeidler', name='andi', cat='nerd', timestamp=DateTime('May 11 1972 03:45 GMT'))
        output = []
        response = getData('add_response.txt')
        fakehttp(proc.getConnection(), response, output)    # fake add response
        proc.index(foo)
        output = ''.join(output).replace('\r', '')
        required = '<field name="timestamp">1972-05-11T03:45:00.000Z</field>'
        self.assert_(output.find(required) > 0, '"date" data not found')

    def testReindexObject(self):
        proc = self.proc
        output = []
        response = getData('add_response.txt')
        fakehttp(proc.getConnection(), response, output)    # fake add response
        proc.reindex(Foo(id='500', name='python test doc')) # reindexing sends data
        output = ''.join(output).replace('\r', '')
        self.assertEqual(output, getData('add_request.txt'))

    def testUnindexObject(self):
        proc = self.proc
        output = []
        response = getData('delete_response.txt')
        fakehttp(proc.getConnection(), response, output)    # fake response
        proc.unindex(Foo(id='500', name='python test doc')) # unindexing sends data
        output = ''.join(output).replace('\r', '')
        self.assertEqual(output, getData('delete_request.txt'))

    def testCommit(self):
        proc = self.proc
        output = []
        response = getData('commit_response.txt')
        fakehttp(proc.getConnection(), response, output)    # fake response
        proc.commit()                                       # committing sends data
        output = ''.join(output).replace('\r', '')
        self.assertEqual(output, getData('commit_request.txt'))


class ThreadedConnectionTests(TestCase):

    def testLocalConnections(self):
        proc = SolrIndexQueueProcessor()
        proc.setHost()
        schema = getData('schema.xml')
        log = []
        def runner():
            fakehttp(proc.getConnection(), schema, [])  # fake schema response
            proc.getSchema()                            # read and cache the schema
            output = []
            response = getData('add_response.txt')
            fakehttp(proc.getConnection(), response, output)    # fake add response
            proc.index(Foo(id='500', name='python test doc'))   # indexing sends data
            proc.closeConnection()
            log.append(''.join(output).replace('\r', ''))
            log.append(proc)
            log.append(proc.getConnection())
        # after the runner was set up, another thread can be created and
        # started;  its output should contain the proper indexing request,
        # whereas the main thread's connection remain idle;  the latter
        # cannot be checked directly, but the connection object would raise
        # an exception if it was used to send a request without setting up
        # a fake response beforehand...
        thread = Thread(target=runner)
        thread.start()
        thread.join()
        conn = proc.getConnection()         # get this thread's connection
        fakehttp(conn, schema, [])          # fake schema response
        proc.getSchema()                    # read and cache the schema
        proc.closeConnection()
        self.assertEqual(len(log), 3)
        self.assertEqual(log[0], getData('add_request.txt'))
        self.failUnless(isinstance(log[1], SolrIndexQueueProcessor))
        self.failUnless(isinstance(log[2], SolrConnection))
        self.failUnless(isinstance(proc, SolrIndexQueueProcessor))
        self.failUnless(isinstance(conn, SolrConnection))
        self.assertEqual(log[1], proc)      # processors should be the same...
        self.assertNotEqual(log[2], conn)   # but not the connections


def test_suite():
    return TestSuite([
        makeSuite(QueueIndexerTests),
        makeSuite(ThreadedConnectionTests),
    ])

if __name__ == '__main__':
    main(defaultTest='test_suite')

