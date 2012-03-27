import unittest
import logging
logging.basicConfig()
import subprocess
from tempfile import mkdtemp

from checks.db.mongo import MongoDb

PORT1 = 27017
PORT2 = 37017

class TestMongo(unittest.TestCase):
    def setUp(self):
        self.c = MongoDb(logging.getLogger(__file__))
        # Start 2 instances of Mongo
        dir1 = mkdtemp()
        dir2 = mkdtemp()
        self.p1 = subprocess.Popen(["mongod", "--dbpath", dir1, "--port", str(PORT1)],
                                   executable="mongod",
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        self.p2 = subprocess.Popen(["mongod", "--dbpath", dir2, "--port", str(PORT2)],
                                   executable="mongod",
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)

    def tearDown(self):
        self.p1.terminate()
        self.p2.terminate()

    # def testCheck(self):
    #     r = self.c.check({"mongodb_server": "localhost", "mongodb_port": PORT1})
    #     self.assertEquals(r["connections"]["current"], 1)

    def testCheckMultipleInstances(self):
        r = self.c.check({"mongo":
                            {"first": {"server": "localhost", "port": PORT1},
                            "second": {"server": "localhost", "port": PORT2}}})
        self.assertEquals(r["connections"]["current"], 1)

if __name__ == '__main__':
    unittest.main()
        
