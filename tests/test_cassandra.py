import logging
import unittest
import os
import os.path

from nose.plugins.attrib import attr

from checks.cassandra import Cassandra
from dogstream.cassandra import parse_cassandra



logger = logging.getLogger(__name__)

class TestCassandra(unittest.TestCase):
    def setUp(self):
        self.info = open(os.path.join(os.path.dirname(__file__), "cassandra", "info"), "r").read()
        self.info8 = open(os.path.join(os.path.dirname(__file__), "cassandra", "info.8"), "r").read()
        self.tpstats = open(os.path.join(os.path.dirname(__file__), "cassandra", "tpstats"), "r").read()
        self.tpstats8 = open(os.path.join(os.path.dirname(__file__), "cassandra", "tpstats.8"), "r").read()
        self.cfstats = open(os.path.join(os.path.dirname(__file__), "cassandra", "cfstats"), "r").read()
        self.info_opp = open(os.path.join(os.path.dirname(__file__), "cassandra", "info.opp"), "r").read()
        self.c = Cassandra()
        
    def tearDown(self):
        pass

    @attr('cassandra')
    def testParseInfoOpp(self):
        # Assert we can parse info from nodes using the order preserving
        # partitioner, event if we dont' do anything with the token.
        res = {}
        self.c._parseInfo(self.info_opp, res, logger)
        self.assertEquals(res.get("load"), 304803091578.0)

        
    @attr('cassandra')
    def testParseInfo(self):
        res = {}
        # v0.7
        self.c._parseInfo(self.info, res, logger)
        self.assertNotEquals(len(res.keys()), 0)
        self.assertEquals(res.get("load"), 467988.0)
        self.assertEquals(res.get("uptime"), 95)
        self.assertEquals(res.get("heap_used"), 521.86)
        self.assertEquals(res.get("heap_total"), 1019.88)
        # v0.8
        res = {}
        self.c._parseInfo(self.info8, res, logger)
        self.assertNotEquals(len(res.keys()), 0)
        self.assertEquals(res.get("load"), 304803091578.0)
        self.assertEquals(res.get("uptime"), 188319)
        self.assertEquals(res.get("heap_used"), 2527.04)
        self.assertEquals(res.get("heap_total"), 3830.0)
        self.assertEquals(res.get("datacenter"), 28)
        self.assertEquals(res.get("rack"), 76)
        self.assertEquals(res.get("exceptions"), 0)
        
    @attr('cassandra')
    def testParseCfstats(self):
        res = {}
        self.c._parseCfstats(self.cfstats, res)
        self.assertNotEquals(len(res.keys()), 0)
        
    @attr('cassandra')
    def testParseTpstats(self):
        res = {}
        self.c._parseTpstats(self.tpstats, res)
        self.assertNotEquals(len(res.keys()), 0)

class TestCassandraDogstream(unittest.TestCase):
    @attr('cassandra')
    def testStart(self):
        events = parse_cassandra(logger, " INFO [main] 2012-12-11 21:46:26,995 StorageService.java (line 687) Bootstrap/Replace/Move completed! Now serving reads.")
        self.assertIsNone(events)

    @attr('cassandra')
    def testInfo(self):
        events = parse_cassandra(logger, " INFO [CompactionExecutor:35] 2012-12-02 21:15:03,738 AutoSavingCache.java (line 268) Saved KeyCache (5 items) in 3 ms")
        self.assertIsNone(events)

    @attr('cassandra')
    def testWarn(self):
        events = parse_cassandra(logger, " WARN [MemoryMeter:1] 2012-12-03 20:07:47,158 Memtable.java (line 197) setting live ratio to minimum of 1.0 instead of 0.9416553595658074")
        self.assertIsNone(events)

    @attr('cassandra')
    def testError(self):
        for line in """\
ERROR [CompactionExecutor:518] 2012-12-11 21:35:29,686 AbstractCassandraDaemon.java (line 135) Exception in thread Thread[CompactionExecutor:518,1,RMI Runtime]
java.util.concurrent.RejectedExecutionException
        at java.util.concurrent.ThreadPoolExecutor$AbortPolicy.rejectedExecution(ThreadPoolExecutor.java:1768)
        at java.util.concurrent.ThreadPoolExecutor.reject(ThreadPoolExecutor.java:767)
        at java.util.concurrent.ScheduledThreadPoolExecutor.delayedExecute(ScheduledThreadPoolExecutor.java:215)
        at java.util.concurrent.ScheduledThreadPoolExecutor.schedule(ScheduledThreadPoolExecutor.java:397)
        at java.util.concurrent.ScheduledThreadPoolExecutor.submit(ScheduledThreadPoolExecutor.java:470)
        at org.apache.cassandra.io.sstable.SSTableDeletingTask.schedule(SSTableDeletingTask.java:67)
        at org.apache.cassandra.io.sstable.SSTableReader.releaseReference(SSTableReader.java:806)
        at org.apache.cassandra.db.DataTracker.removeOldSSTablesSize(DataTracker.java:358)
        at org.apache.cassandra.db.DataTracker.postReplace(DataTracker.java:330)
        at org.apache.cassandra.db.DataTracker.replace(DataTracker.java:324)
        at org.apache.cassandra.db.DataTracker.replaceCompactedSSTables(DataTracker.java:253)
        at org.apache.cassandra.db.ColumnFamilyStore.replaceCompactedSSTables(ColumnFamilyStore.java:992)
        at org.apache.cassandra.db.compaction.CompactionTask.execute(CompactionTask.java:200)
        at org.apache.cassandra.db.compaction.CompactionManager$1.runMayThrow(CompactionManager.java:154)
        at org.apache.cassandra.utils.WrappedRunnable.run(WrappedRunnable.java:30)
        at java.util.concurrent.Executors$RunnableAdapter.call(Executors.java:441)
        at java.util.concurrent.FutureTask$Sync.innerRun(FutureTask.java:303)
        at java.util.concurrent.FutureTask.run(FutureTask.java:138)
        at java.util.concurrent.ThreadPoolExecutor$Worker.runTask(ThreadPoolExecutor.java:886)
        at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:908)
        at java.lang.Thread.run(Thread.java:662)""".splitlines():
            events = parse_cassandra(logger, line)
            self.assertIsNone(events)

    @attr('cassandra')
    def testCompactionStart(self):
        events = parse_cassandra(logger, " INFO [CompactionExecutor:2] 2012-12-11 21:46:27,012 CompactionTask.java (line 109) Compacting [SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-11-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-9-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-12-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-10-Data.db')]")
        self.assertEquals(events,[{'alert_type': 'info', 'event_type': 'cassandra.compaction', 'timestamp': 1355262387, 'msg_title': "Compacting [SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-1", 'msg_text': "Compacting [SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-11-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-9-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-12-Data.db'), SSTableReader(path='/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-10-Data.db')]", 'auto_priority': 0}])

    @attr('cassandra')
    def testCompactionEnd(self):
        events = parse_cassandra(logger, "INFO [CompactionExecutor:2] 2012-12-11 21:46:27,095 CompactionTask.java (line 221) Compacted to [/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-13-Data.db,].  880 to 583 (~66% of original) bytes for 4 keys at 0.007831MB/s.  Time: 71ms.")
        self.assertEquals(events,[{'alert_type': 'info', 'event_type': 'cassandra.compaction', 'timestamp': 1355262387, 'msg_title': 'Compacted to [/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-13-Data.db,].  880 ', 'msg_text': 'Compacted to [/var/lib/cassandra/data/system/LocationInfo/system-LocationInfo-he-13-Data.db,].  880 to 583 (~66% of original) bytes for 4 keys at 0.007831MB/s.  Time: 71ms.', 'auto_priority': 0}])

if __name__ == '__main__':
    unittest.main()
