#!/usr/bin/env python

import boto3
import botocore
import inspect
import json
import math
import os
import pprint
import random
import sys
import time
import types

sys.path.insert(0, "%s/lib/util" % os.path.dirname(os.path.abspath(__file__)))
import Cons
import Util

sys.path.insert(0, "%s/lib" % os.path.dirname(os.path.abspath(__file__)))
import Ec2Region

import LaunchOnDemandInsts
import ReqSpotInsts


def main(argv):
  job_list = []
  for k, v in globals().iteritems():
    if type(v) != types.FunctionType:
      continue
    if k.startswith("Job_"):
      job_list.append(k[4:])
  #Cons.P(job_list)

  if len(argv) != 2:
    Cons.P("Usage: %s job_name" % argv[0])
    Cons.P("  Jobs available:")
    Cons.P(Util.Indent("\n".join(sorted(job_list)), 4))
    sys.exit(1)

  job = "Job_" + argv[1]

  # http://stackoverflow.com/questions/3061/calling-a-function-of-a-module-from-a-string-with-the-functions-name-in-python
  globals()[job]()



# A workload type per an EC2 instance for now, but nothing's stopping you running different types of workloads in an instance.
def Job_Ycsb_Mutant():
  # Job conf per EC2 inst
  class ConfEc2Inst:
    exp_per_ec2inst = 31

    def __init__(self):
      self.params = []
    def Full(self):
      return (len(self.params) >= ConfEc2Inst.exp_per_ec2inst)
    def Add(self, params):
      self.params.append(params)
    def Size(self):
      return len(self.params)
    def __repr__(self):
      return "%s" % (self.params)

  workload_type = "a"
  slow_stg_dev = "ebs-st1"

  # SSTable OTT (organization temperature threshold)
  # Target IOPSes
  sstott_targetiops = {
      2**(-12): [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(-10): [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(-8):  [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(-6):  [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(-4):  [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(-2):  [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(0):   [1000, 10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000]
    , 2**(12): [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    , 2**(14): [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    , 2**(16): [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    , 2**(18): [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000]
    }
  for sst_ott, targetiops in sstott_targetiops.iteritems():
    random.shuffle(sstott_targetiops[sst_ott])

  confs_ec2 = []
  conf_ec2 = ConfEc2Inst()
  for i in range(4):
    for sst_ott, targetiops in sorted(sstott_targetiops.iteritems()):
      for ti in targetiops:
        if conf_ec2.Full():
          confs_ec2.append(conf_ec2)
          conf_ec2 = ConfEc2Inst()
        conf_ec2.Add((ti, sst_ott))
  if conf_ec2.Size() > 0:
    confs_ec2.append(conf_ec2)

  Cons.P("%d machine(s)" % len(confs_ec2))
  # sys.exit(1)
  Cons.P(pprint.pformat(confs_ec2, width=100))

  for conf_ec2 in confs_ec2:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        , "init_script": "mutant-rocksdb"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "ec2_tag_Name": inspect.currentframe().f_code.co_name[4:] + "-workload" + workload_type + "-stg_" + slow_stg_dev 
        # Initialize local SSD by erasing. Some EC2 instance types need this.
        , "erase_local_ssd": "true"
        , "unzip_quizup_data": "false"
        , "run_cassandra_server": "false"
        , "rocksdb": {}  # This doesn't do much other than checking out the code and building.
        , "rocksdb-quizup-runs": []
        , "ycsb-runs": []
        , "terminate_inst_when_done": "true"
        }
    if slow_stg_dev == "ebs-st1":
      # 40 MiB/s/TiB. With 3 TiB, 120 MiB/sec.
      #   This should be good enough.
      #     With a local SSD experiment, the average throughput tops at 35 MB/s. Although 99th percentile goes up to 260 MB/s.
      #     You can check with the dstat local ssd log.
      #     However, the saturation happens way earlier than that. Check with the experiment results.
      #   However, regardless of the throughput number, st1 is really slow in practice.
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    else:
      raise RuntimeError("Unexpected")

    ycsb_runs = {
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
			, "workload_type": workload_type
      , "db_path": "/mnt/local-ssd1/rocksdb-data/ycsb"
      , "db_stg_dev_paths": [
          "/mnt/local-ssd1/rocksdb-data/ycsb/t0"
          , "/mnt/%s/rocksdb-data-t1" % slow_stg_dev]
      , "runs": []
      }

    # TODO: I'm concerned about the initial bulk SSTable migration. Or should I?
    #   We'll see the result and think about it. We'll have to gather all raw log files.
    #   If that's the case, we'll have to exclude the initial warm up period.
    for p in conf_ec2.params:
      target_iops = p[0]
      sst_ott = p[1]
      op_cnt = 10000000 / 2
      if target_iops < 10000:
        op_cnt = op_cnt / 10
      ycsb_runs["runs"].append({
        "load": {
          #"use_preloaded_db": ""
          "use_preloaded_db": "ycsb-%s-10M-records-rocksdb" % workload_type
          , "ycsb_params": " -p recordcount=10000000 -target 10000"
          }
        , "run": {
          "evict_cached_data": "true"
          , "memory_limit_in_mb": 5.0 * 1024
          # , "ycsb_params": " -p recordcount=10000000 -p operationcount=%d -p readproportion=0.95 -p insertproportion=0.05 -target %d" % (op_cnt, target_iops)
          , "ycsb_params": " -p recordcount=10000000 -p operationcount=%d -target %d" % (op_cnt, target_iops)
          }
        # Mutant doesn't trigger any of these by default: it behaves like unmodified RocksDB.
        , "mutant_options": {
          "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "sst_ott": sst_ott
          , "cache_filter_index_at_all_levels": "true"
          # Replaying a workload in the past
          #, "replaying": {
          #  "simulated_time_dur_sec": 1365709.587
          #  , "simulation_time_dur_sec": 60000
          #  }
          , "db_stg_dev_paths": ycsb_runs["db_stg_dev_paths"]
          }
        })

    params["ycsb-runs"] = dict(ycsb_runs)
    LaunchJob(params)


def Job_Ycsb_Rocksdb():
  # Job conf per EC2 inst
  class ConfEc2Inst:
    exp_per_ec2inst = 8

    def __init__(self):
      self.params = []
    def Full(self):
      return (len(self.params) >= ConfEc2Inst.exp_per_ec2inst)
    def Add(self, params):
      self.params.append(params)
    def Size(self):
      return len(self.params)
    def __repr__(self):
      return "%s" % (self.params)

  workload_type = "a"

  # db_stg_dev = "ebs-st1"
  db_stg_dev = "local-ssd1"

  if db_stg_dev == "local-ssd1":
    target_iops_range = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000 \
        , 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 19000, 20000]
  elif db_stg_dev == "ebs-st1":
    target_iops_range = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
  random.shuffle(target_iops_range)

  confs_ec2 = []
  conf_ec2 = ConfEc2Inst()
  for i in range(5):
    for ti in target_iops_range:
      if conf_ec2.Full():
        confs_ec2.append(conf_ec2)
        conf_ec2 = ConfEc2Inst()
      conf_ec2.Add(ti)
  if conf_ec2.Size() > 0:
    confs_ec2.append(conf_ec2)

  Cons.P("%d machine(s)" % len(confs_ec2))
  Cons.P(pprint.pformat(confs_ec2, width=100))

  for conf_ec2 in confs_ec2:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        , "init_script": "mutant-rocksdb"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "ec2_tag_Name": inspect.currentframe().f_code.co_name[4:] + "-workload" + workload_type + "-stg_" + db_stg_dev 
        # Initialize local SSD by erasing. Some EC2 instance types need this.
        , "erase_local_ssd": "true"
        , "unzip_quizup_data": "false"
        , "run_cassandra_server": "false"
        , "rocksdb": {}  # This doesn't do much other than checking out the code and building.
        , "rocksdb-quizup-runs": []
        , "ycsb-runs": []
        , "terminate_inst_when_done": "true"
        }
    if db_stg_dev == "ebs-st1":
      # 40 MiB/s/TiB. With 3 TiB, 120 MiB/sec.
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif db_stg_dev == "local-ssd1":
      pass
    else:
      raise RuntimeError("Unexpected")

    ycsb_runs = {
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "workload_type": workload_type
      , "db_path": "/mnt/%s/rocksdb-data/ycsb" % db_stg_dev
      , "db_stg_dev_paths": [
          "/mnt/%s/rocksdb-data/ycsb/t0" % db_stg_dev]
      , "runs": []
      }

    for target_iops in conf_ec2.params:
      op_cnt = 10000000 / 2
      if target_iops < 10000:
        op_cnt = op_cnt / 10
      ycsb_runs["runs"].append({
        # The load phase needs to be slow. Otherwise, the SSTables get too big. Probably because of the pending compactions,
        #   which will affect the performance of in the run phase.
        #   However, with a slow loading like with -target 10000, it takes 16 mins.
        # Decided to keep the DB image in S3. Takes about 1 min to sync.
        "load": {
          #"use_preloaded_db": ""
          # This can be used for any devices. Now the name is misleading, but ok.
          "use_preloaded_db": "ycsb-%s-10M-records-rocksdb" % workload_type
          , "ycsb_params": " -p recordcount=10000000 -target 10000"
          }
        # How long it takes when the system gets saturated.
        #   Without memory throttling, 10M reqs: 101 sec.
        #                              30M reqs: 248 sec
        #   With a 4GB memory throttling, 10M reqs: 119 sec. Not a lot of difference. Hmm.
        #                                 30M reqs: 305 sec. Okay.
        #
        # 11G of data. With 5GB, JVM seems to be doing just fine.
        # Out of the 30M operations, 0.95 of them are reads; 0.05 are writes.
        #   With the raw latency logging, YCSB hogs more memory: it keeps the data in memory.
        , "run": {
          "evict_cached_data": "true"
          , "memory_limit_in_mb": 5.0 * 1024
          # Mutant doesn't trigger any of these by default: it behaves like unmodified RocksDB.
          # , "ycsb_params": " -p recordcount=10000000 -p operationcount=%s -p readproportion=0.95 -p insertproportion=0.05 -target %d" % (op_cnt, target_iops)
          , "ycsb_params": " -p recordcount=10000000 -p operationcount=%s -target %d" % (op_cnt, target_iops)
          }
        , "mutant_options": {
          "monitor_temp": "false"
          , "migrate_sstables": "false"
          , "sst_ott": 0
          , "cache_filter_index_at_all_levels": "false"
          # Replaying a workload in the past
          #, "replaying": {
          #  "simulated_time_dur_sec": 1365709.587
          #  , "simulation_time_dur_sec": 60000
          #  }
          , "db_stg_dev_paths": ycsb_runs["db_stg_dev_paths"]
          }
        })

    params["ycsb-runs"] = dict(ycsb_runs)
    LaunchJob(params)


# TODO: How are workload d and Zipfian different?
#   what does the workload d do? what portion of the latest records does it read?

def Job_Ycsb_B_Rocksdb():
  # Job conf per EC2 inst
  class ConfEc2Inst:
    exp_per_ec2inst = 7

    def __init__(self):
      self.params = []
    def Full(self):
      return (len(self.params) >= ConfEc2Inst.exp_per_ec2inst)
    def Add(self, params):
      self.params.append(params)
    def Size(self):
      return len(self.params)
    def __repr__(self):
      return "%s" % (self.params)

  #db_stg_dev = "ebs-st1"
  db_stg_dev = "local-ssd1"

  workload_type = "b"

  if db_stg_dev == "local-ssd1":
    target_iops_range = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, \
          10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, \
          100000, 110000, 120000]
  elif db_stg_dev == "ebs-st1":
    target_iops_range = [1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
  random.shuffle(target_iops_range)

  confs_ec2 = []
  # Target IOPSes
  conf_ec2 = ConfEc2Inst()
  for i in range(5):
    # Target IOPS
    for ti in target_iops_range:
      if conf_ec2.Full():
        confs_ec2.append(conf_ec2)
        conf_ec2 = ConfEc2Inst()
      conf_ec2.Add(ti)
  if conf_ec2.Size() > 0:
    confs_ec2.append(conf_ec2)

  #confs_ec2 = confs_ec2[0:1]
  Cons.P("%d machine(s)" % len(confs_ec2))
  Cons.P(pprint.pformat(confs_ec2, width=100))
  #sys.exit(1)

  for conf_ec2 in confs_ec2:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        , "init_script": "mutant-rocksdb"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "ec2_tag_Name": inspect.currentframe().f_code.co_name[4:]
        # Initialize local SSD by erasing. Some EC2 instance types need this.
        , "erase_local_ssd": "true"
        , "unzip_quizup_data": "false"
        , "run_cassandra_server": "false"
        , "rocksdb": {}  # This doesn't do much other than checking out the code and building.
        , "rocksdb-quizup-runs": []
        , "ycsb-runs": []
        , "terminate_inst_when_done": "true"
        }
    if db_stg_dev == "ebs-st1":
      # 40 MiB/s/TiB. With 3 TiB, 120 MiB/sec.
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif db_stg_dev == "local-ssd1":
      pass
    else:
      raise RuntimeError("Unexpected")

    ycsb_runs = {
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "workload_type": workload_type
      , "db_path": "/mnt/%s/rocksdb-data/ycsb" % db_stg_dev
      , "db_stg_dev_paths": [
          "/mnt/%s/rocksdb-data/ycsb/t0" % db_stg_dev]
      , "runs": []
      }

    for target_iops in conf_ec2.params:
      ycsb_runs["runs"].append({
        "load": {
          #"use_preloaded_db": ""
          "use_preloaded_db": "ycsb-%s-10M-records-rocksdb" % workload_type
          # For some reason, using the preloaded rocksdb to st1 didn't work. Make a DB snapshot that was loaded on st1.
          #"use_preloaded_db": "ycsb-d-10M-records-rocksdb-st1"
          # Let's try the same one for local ssd. Hope it works. Hope the difference is the separate t0 directory.
          , "ycsb_params": " -p recordcount=10000000 -target 10000"
          # Useful when taking DB snapshots
          , "stop_after_load": "false"
          }
        , "run": {
          "evict_cached_data": "true"
          , "memory_limit_in_mb": 5.0 * 1024
          # Mutant doesn't trigger any of these by default: it behaves like unmodified RocksDB.
          , "ycsb_params": " -p recordcount=10000000 -p operationcount=10000000 -target %d" % target_iops
          }
        , "mutant_options": {
          "monitor_temp": "false"
          , "migrate_sstables": "false"
          , "sst_ott": 0
          , "cache_filter_index_at_all_levels": "false"
          # Replaying a workload in the past
          #, "replaying": {
          #  "simulated_time_dur_sec": 1365709.587
          #  , "simulation_time_dur_sec": 60000
          #  }
          , "db_stg_dev_paths": ycsb_runs["db_stg_dev_paths"]
          }
        })

    params["ycsb-runs"] = dict(ycsb_runs)
    LaunchJob(params)


def Job_QuizupMutantSlaAdmin():
  params = {
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      , "init_script": "mutant-rocksdb"
      , "ami_name": "mutant-rocksdb"
      , "block_storage_devs": [{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}]
      , "ec2_tag_Name": inspect.currentframe().f_code.co_name[4:]
      , "erase_local_ssd": "true"
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": [
        {
          # Use the current function name since you always forget to set this
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "true"
          , "evict_cached_data": "true"
          , "memory_limit_in_mb": 2.0 * 1024

          # Not caching metadata might be a better idea. So the story is you
          # present each of the optimizations separately, followed by the
          # combined result.
          #, "cache_filter_index_at_all_levels": "false"

          # Cache metadata for a comparison
          , "cache_filter_index_at_all_levels": "true"

          , "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "workload_start_from": 0.899
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 60000
          , "sst_migration_temperature_threshold": 1.0
          }
        ]
      , "terminate_inst_when_done": "false"
      }
  LaunchJob(params)

def Job_Quizup2LevelMutantStorageUsageBySstMigTempThresholds():
  class Conf:
    exp_per_ec2inst = 1
    def __init__(self, slow_dev):
      self.slow_dev = slow_dev
      self.sst_mig_temp_thrds = []
    def Full(self):
      return (len(self.sst_mig_temp_thrds) >= Conf.exp_per_ec2inst)
    def Add(self, mem_size):
      self.sst_mig_temp_thrds.append(mem_size)
    def Size(self):
      return len(self.sst_mig_temp_thrds)
    def __repr__(self):
      return "(%s, %s)" % (self.slow_dev, self.sst_mig_temp_thrds)

  # [0.25, 256]
  for i in range(-2, 9):
    #Cons.P("%d %f" % (i, math.pow(2, i)))
    mig_temp_thrds = math.pow(2, i)

  num_exp_per_conf = 3
  confs = []
  for slow_dev in ["ebs-gp2"]:
    conf = Conf(slow_dev)
    for j in range(num_exp_per_conf):
      for sst_mig_temp_thrds in [10.0, 12.0, 14.0, 16, 20, 24, 30, 38, 48, 60, 72, 96, 128]: 
      # , 16.0, 24.0, 32.0, 40.0, 48.0, 64.0, 96.0, 128.0, 192.0, 256.0]: # 2^10
        if conf.Full():
          confs.append(conf)
          conf = Conf(slow_dev)
        conf.Add(sst_mig_temp_thrds)
    if conf.Size() > 0:
      confs.append(conf)

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))
  #sys.exit(1)

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-cassandra-server"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.slow_dev == "ebs-gp2":
      # 100GB gp2: 300 baseline IOPS. 2,000 burst IOPS.
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 100, "DeviceName": "d"})
    else:
      raise RuntimeError("Unexpected")

    for mt in conf.sst_mig_temp_thrds:
      p1 = { \
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {"t1": "/mnt/%s/rocksdb-data-quizup-t1" % conf.slow_dev}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "false"
          , "evict_cached_data": "true"
          # 9GB memory to cache everything in memory.
          , "memory_limit_in_mb": 9.0 * 1024

          , "cache_filter_index_at_all_levels": "true"
          , "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "workload_start_from": -1.0
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 2000
          , "sst_migration_temperature_threshold": mt
          }
      params["rocksdb-quizup-runs"].append(dict(p1))
    #Cons.P(pprint.pformat(params))
    LaunchJob(params)


def Job_QuizupSstMigTempThresholds_LocalSsd1EbsSt1():
  params = { \
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      , "block_storage_devs": [{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}]
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }

  simulate_full_time_range = False
  simulate_from_90p_time_range = True

  # Full time range experiments. For calculating the storage cost.
  if simulate_full_time_range:
    for sst_mig_temp_thrds in [
      0.015625, 
      0.25, 
      0.75, 
      2, 
      4, 
      6, 
      10, 
      14, 
      20, 
      24, 
      38, 
      96, 
      128, 
      256, 
      ]:  # 2^10
      p1 = { \
          # Use the current function name since you always forget to set this
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {"t1": "/mnt/local-ssd1/rocksdb-data-quizup/t1"}
          # You don't need to use the slow device for calculating cost
          #, "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "false"
          , "evict_cached_data": "true"
          , "memory_limit_in_mb": 9.0 * 1024

          # This doesn't really matter for measuring the number of compactions
          # and SSTables.
          , "cache_filter_index_at_all_levels": "false"
          , "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "workload_start_from": -1.0
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 2000
          , "sst_migration_temperature_threshold": sst_mig_temp_thrds
          }
      params["rocksdb-quizup-runs"] = []
      params["rocksdb-quizup-runs"].append(dict(p1))
      Cons.P(pprint.pformat(params))
      LaunchJob(params)

  # 95% to 100% time range experiments for measuring latency and the number of IOs.
  if simulate_from_90p_time_range:
    class Conf:
      exp_per_ec2inst = 3
      def __init__(self):
        self.sst_mig_temp_thrds = []
      def Full(self):
        return (len(self.sst_mig_temp_thrds) >= Conf.exp_per_ec2inst)
      def Add(self, smtt):
        self.sst_mig_temp_thrds.append(smtt)
      def Size(self):
        return len(self.sst_mig_temp_thrds)
      def __repr__(self):
        return "(%s)" % (self.sst_mig_temp_thrds)

    num_exp_per_conf = 4 
    confs = []
    conf = Conf()
    for j in range(num_exp_per_conf):
      # From 2^-10 = 0.0009765625 down to 2^-36
      #for i in range(-10, -38, -2):
      #for i in range(10, -10, -2):
      for sst_mig_temp_thrds in [
        # 0.015625, 
        0.25, 
        0.75, 
        2, 
        4, 
        6, 
        # 10, 
        14, 
        # 20, 
        # 24, 
        38, 
        # 96, 
        # 128, 
        256, 
      ]:
        if conf.Full():
          confs.append(conf)
          conf = Conf()
        conf.Add(sst_mig_temp_thrds)
    if conf.Size() > 0:
      confs.append(conf)

    Cons.P("%d machines" % len(confs))
    Cons.P(pprint.pformat(confs, width=100))
    # sys.exit(1)

    for conf in confs:
      params["rocksdb-quizup-runs"] = []
      for mt in conf.sst_mig_temp_thrds:
        p1 = { \
            # Use the current function name since you always forget to set this
            "exp_desc": inspect.currentframe().f_code.co_name[4:]
            , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
            , "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
            , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
            , "init_db_to_90p_loaded": "true"
            , "evict_cached_data": "true"
            , "memory_limit_in_mb": 2.0 * 1024

            # Not caching metadata might be a better idea. So the story is you
            # present each of the optimizations separately, followed by the
            # combined result.
            #, "cache_filter_index_at_all_levels": "false"

            # Cache metadata for a comparison
            , "cache_filter_index_at_all_levels": "true"

            , "monitor_temp": "true"
            , "migrate_sstables": "true"
            , "workload_start_from": 0.899
            , "workload_stop_at":    -1.0
            , "simulation_time_dur_in_sec": 60000
            , "sst_migration_temperature_threshold": mt
            }
        params["rocksdb-quizup-runs"].append(dict(p1))
      #Cons.P(pprint.pformat(params))
      LaunchJob(params)


def Job_QuizupLowSstMigTempThresholds_LocalSsd1Only():
  params = { \
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      , "block_storage_devs": []
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }

  # Full time range experiments are for the number of compactions and SSTables.
  # They don't show the number of disk IOs.
  if False:
    # From 2^-10 = 0.0009765625 down to 2^-32
    for i in range(-10, -34, -2):
      sst_mig_temp_thrds = pow(2, i)
      p1 = { \
          # Use the current function name since you always forget to set this
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "false"
          , "evict_cached_data": "true"
          , "memory_limit_in_mb": 9.0 * 1024

          # This doesn't really matter for measuring the number of compactions
          # and SSTables.
          , "cache_filter_index_at_all_levels": "false"
          , "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "workload_start_from": -1.0
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 20000
          , "sst_migration_temperature_threshold": sst_mig_temp_thrds
          }
      params["rocksdb-quizup-runs"] = []
      params["rocksdb-quizup-runs"].append(dict(p1))
      #Cons.P(pprint.pformat(params))
      LaunchJob(params)

  # 95% to 100% time range experiments for measuring latency and the number of IOs.
  if True:
    class Conf:
      exp_per_ec2inst = 2
      def __init__(self):
        self.sst_mig_temp_thrds = []
      def Full(self):
        return (len(self.sst_mig_temp_thrds) >= Conf.exp_per_ec2inst)
      def Add(self, smtt):
        self.sst_mig_temp_thrds.append(smtt)
      def Size(self):
        return len(self.sst_mig_temp_thrds)
      def __repr__(self):
        return "(%s)" % (self.sst_mig_temp_thrds)

    num_exp_per_conf = 2
    confs = []
    conf = Conf()
    for j in range(num_exp_per_conf):
      # From 2^-10 = 0.0009765625 down to 2^-32
      for i in range(-10, -34, -2):
        if conf.Full():
          confs.append(conf)
          conf = Conf()
        mig_temp_thrds = math.pow(2, i)
        conf.Add(mig_temp_thrds)
    if conf.Size() > 0:
      confs.append(conf)

    Cons.P("%d machines" % len(confs))
    Cons.P(pprint.pformat(confs, width=100))
    sys.exit(1)

    for conf in confs:
      params["rocksdb-quizup-runs"] = []
      for mt in conf.sst_mig_temp_thrds:
        p1 = { \
            # Use the current function name since you always forget to set this
            "exp_desc": inspect.currentframe().f_code.co_name[4:]
            , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
            , "slow_dev_paths": {}
            , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
            , "init_db_to_90p_loaded": "true"
            , "evict_cached_data": "true"
            , "memory_limit_in_mb": 2.0 * 1024

            # Not caching metadata might be a better idea. So the story is you
            # present each of the optimizations separately, followed by the
            # combined result.
            , "cache_filter_index_at_all_levels": "false"
            , "monitor_temp": "true"
            , "migrate_sstables": "true"
            , "workload_start_from": 0.899
            , "workload_stop_at":    -1.0
            , "simulation_time_dur_in_sec": 60000
            , "sst_migration_temperature_threshold": mt
            }
        params["rocksdb-quizup-runs"].append(dict(p1))
      #Cons.P(pprint.pformat(params))
      LaunchJob(params)


# TODO: clean up
def Job_QuizupToCleanup2LevelMutantBySstMigTempThresholdsToMeasureStorageUsage():
  class Conf:
    exp_per_ec2inst = 2
    def __init__(self, slow_dev):
      self.slow_dev = slow_dev
      self.sst_mig_temp_thrds = []
    def Full(self):
      return (len(self.sst_mig_temp_thrds) >= Conf.exp_per_ec2inst)
    def Add(self, mem_size):
      self.sst_mig_temp_thrds.append(mem_size)
    def Size(self):
      return len(self.sst_mig_temp_thrds)
    def __repr__(self):
      return "(%s, %s)" % (self.slow_dev, self.sst_mig_temp_thrds)

  # [0.25, 256]
  for i in range(-2, 9):
    #Cons.P("%d %f" % (i, math.pow(2, i)))
    mig_temp_thrds = math.pow(2, i)

  num_exp_per_conf = 2
  confs = []
  if True:
    for slow_dev in ["ebs-gp2"]:
      conf = Conf(slow_dev)
      for j in range(num_exp_per_conf):
        #for i in range(-14, 12, 2):
        for i in range(-20, -14, 2):
          if conf.Full():
            confs.append(conf)
            conf = Conf(slow_dev)
          mig_temp_thrds = math.pow(2, i)
          conf.Add(mig_temp_thrds)
      if conf.Size() > 0:
        confs.append(conf)

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-cassandra-server"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.slow_dev == "ebs-gp2":
      # 100GB gp2: 300 baseline IOPS. 2,000 burst IOPS.
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 100, "DeviceName": "d"})
    else:
      raise RuntimeError("Unexpected")

    for mt in conf.sst_mig_temp_thrds:
      p1 = { \
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {"t1": "/mnt/%s/rocksdb-data-quizup-t1" % conf.slow_dev}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "false"
          , "evict_cached_data": "true"
          , "memory_limit_in_mb": 9.0 * 1024

          , "cache_filter_index_at_all_levels": "true"
          , "monitor_temp": "true"
          , "migrate_sstables": "true"
          , "workload_start_from": -1.0
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 20000
          , "sst_migration_temperature_threshold": mt
          }
      params["rocksdb-quizup-runs"].append(dict(p1))
    #Cons.P(pprint.pformat(params))
    LaunchJob(params)
  return

  # RocksDB with temperature monitoring and no sstable migration for a comparision
  params = { \
      # us-east-1, which is where the S3 buckets for experiment are.
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      # RocksDB can use the same AMI
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      , "block_storage_devs": []
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }
  p1 = { \
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
      , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
      , "init_db_to_90p_loaded": "false"
      , "evict_cached_data": "true"
      , "memory_limit_in_mb": 9.0 * 1024

      # Doesn't matter. We are interested in the size only.
      , "cache_filter_index_at_all_levels": "false"

      , "monitor_temp": "true"
      , "migrate_sstables": "false"
      , "workload_start_from": -1.0
      , "workload_stop_at":    -1.0
      , "simulation_time_dur_in_sec": 20000
      , "sst_migration_temperature_threshold": 0
      }
  params["rocksdb-quizup-runs"].append(dict(p1))
  #Cons.P(pprint.pformat(params))
  LaunchJob(params)
  return

  # Unmodified RocksDB too for a comparison
  params = { \
      # us-east-1, which is where the S3 buckets for experiment are.
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      # RocksDB can use the same AMI
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      , "block_storage_devs": []
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }
  p1 = { \
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
      , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
      , "init_db_to_90p_loaded": "false"
      , "evict_cached_data": "true"
      , "memory_limit_in_mb": 9.0 * 1024

      , "cache_filter_index_at_all_levels": "false"
      , "monitor_temp": "false"
      , "migrate_sstables": "false"
      , "workload_start_from": -1.0
      , "workload_stop_at":    -1.0
      , "simulation_time_dur_in_sec": 20000
      , "sst_migration_temperature_threshold": 0
      }
  params["rocksdb-quizup-runs"].append(dict(p1))
  #Cons.P(pprint.pformat(params))
  LaunchJob(params)


def Job_QuizupUnmodifiedRocksDbWithWithoutMetadataCachingByStgDevs():
  class Conf:
    exp_per_ec2inst = 5
    def __init__(self, stg_dev):
      self.stg_dev = stg_dev
      self.metadata_caching = []
    def Full(self):
      return (len(self.metadata_caching) >= Conf.exp_per_ec2inst)
    def Add(self, metadata_caching):
      self.metadata_caching.append(metadata_caching)
    def Size(self):
      return len(self.metadata_caching)
    def __repr__(self):
      return "(%s, %s)" % (self.stg_dev, self.metadata_caching)

  # The lower bound without getting the system overloaded are different for
  # different storage devices.  local-ssd1 and ebs-gp2 have 14, which is 1.4GB,
  # which the range() function sets the lower bound as 12. They are capped by
  # the main memory. OOM killer.  ebs-st1 can go 1.6GB without the storage
  # device overloaded, ebs-sc1 2.0GB.
  num_exp_per_conf = 4
  confs = []
  for stg_dev in ["local-ssd1", "ebs-gp2", "ebs-st1", "ebs-sc1"]:
    conf = Conf(stg_dev)
    for j in range(num_exp_per_conf):
      for i in ["true", "false"]:
        if conf.Full():
          confs.append(conf)
          conf = Conf(stg_dev)
        conf.Add(i)
    if conf.Size() > 0:
      confs.append(conf)

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-cassandra-server"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.stg_dev == "local-ssd1":
      pass
    elif conf.stg_dev == "ebs-gp2":
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"})
    elif conf.stg_dev == "ebs-st1":
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif conf.stg_dev == "ebs-sc1":
      params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
    else:
      raise RuntimeError("Unexpected")

    p1 = { \
        "exp_desc": inspect.currentframe().f_code.co_name[4:]
        , "fast_dev_path": "/mnt/%s/rocksdb-data" % conf.stg_dev
        , "db_path": "/mnt/%s/rocksdb-data/quizup" % conf.stg_dev
        , "init_db_to_90p_loaded": "true"
        , "evict_cached_data": "true"
        , "memory_limit_in_mb": 1024 * 2

        , "cache_filter_index_at_all_levels": None

        , "monitor_temp": "false"
        , "migrate_sstables": "false"
        , "workload_start_from": 0.899
        , "workload_stop_at":    -1.0
        , "simulation_time_dur_in_sec": 60000
        }
    for mc in conf.metadata_caching:
      p1["cache_filter_index_at_all_levels"] = mc
      params["rocksdb-quizup-runs"].append(dict(p1))

    #Cons.P(pprint.pformat(params))
    LaunchJob(params)


def Job_Quizup2LevelMutantLatencyByColdStgBySstMigTempThresholds():
  class Conf:
    exp_per_ec2inst = 4
    def __init__(self, slow_dev):
      self.slow_dev = slow_dev
      self.sst_mig_temp_thrds = []
    def Full(self):
      return (len(self.sst_mig_temp_thrds) >= Conf.exp_per_ec2inst)
    def Add(self, smtt):
      self.sst_mig_temp_thrds.append(smtt)
    def Size(self):
      return len(self.sst_mig_temp_thrds)
    def __repr__(self):
      return "(%s, %s)" % (self.slow_dev, self.sst_mig_temp_thrds)

  # [0.25, 256]
  # for i in range(-2, 9):
  #   #Cons.P("%d %f" % (i, math.pow(2, i)))
  #   mig_temp_thrds = math.pow(2, i)



  num_exp_per_conf = 5 
  confs = []
  # Redo some exps
  if True:
    for slow_dev in ["ebs-gp2", "ebs-st1", "ebs-sc1"]:
      conf = Conf(slow_dev)
      for j in range(num_exp_per_conf):
        for mig_temp_thrds in [
              # 0.015625, 
              0.25, 
              0.75, 
              2, 
              4, 
              6, 
              # 10, 
              14, 
              # 20, 
              # 24, 
              38, 
              # 96, 
              # 128, 
              256, 
        ]: 
          if conf.Full():
            confs.append(conf)
            conf = Conf(slow_dev)
          conf.Add(mig_temp_thrds)
      if conf.Size() > 0:
        confs.append(conf)

  if False:
    num_exp_per_conf = 2
    for slow_dev in ["ebs-st1"]:
      conf = Conf(slow_dev)
      for j in range(num_exp_per_conf):
        for i in range(1, 9):
          if conf.Full():
            confs.append(conf)
            conf = Conf(slow_dev)
          mig_temp_thrds = math.pow(2, i)
          conf.Add(mig_temp_thrds)
      if conf.Size() > 0:
        confs.append(conf)

  if False:
    num_exp_per_conf = 4
    for slow_dev in ["ebs-sc1"]:
      conf = Conf(slow_dev)
      for j in range(num_exp_per_conf):
        for i in range(2, 9):
          if conf.Full():
            confs.append(conf)
            conf = Conf(slow_dev)
          mig_temp_thrds = math.pow(2, i)
          conf.Add(mig_temp_thrds)
      if conf.Size() > 0:
        confs.append(conf)

  if False:
    num_exp_per_conf = 4
    for slow_dev in ["ebs-sc1"]:
      conf = Conf(slow_dev)
      for j in range(num_exp_per_conf):
        for i in range(0, 2):
          if conf.Full():
            confs.append(conf)
            conf = Conf(slow_dev)
          mig_temp_thrds = math.pow(2, i)
          conf.Add(mig_temp_thrds)
      if conf.Size() > 0:
        confs.append(conf)

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))
  # sys.exit(0)

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-cassandra-server"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.slow_dev == "ebs-gp2":
      # 100GB gp2: 300 baseline IOPS. 2,000 burst IOPS.
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 100, "DeviceName": "d"})
    elif conf.slow_dev == "ebs-st1":
      # 1T st1: 40 MiB/s. 250 burst MiB/s. Since most of the requests will be
      # absorbed by local SSD, I think you can go a lot lower than this.
      # Redo some of the experiment with a 3T disk. From SSTable migration temperature threshold 2.
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif conf.slow_dev == "ebs-sc1":
      # 1T sc1: 12 MiB/s. 80 burst MiB/s
      # Redo some of the experiment with a 3T disk. From SSTable migration temperature threshold 4.
      params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
    else:
      raise RuntimeError("Unexpected")

    for mt in conf.sst_mig_temp_thrds:
      p1 = { \
          "exp_desc": inspect.currentframe().f_code.co_name[4:]
          , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
          , "slow_dev_paths": {"t1": "/mnt/%s/rocksdb-data-quizup-t1" % conf.slow_dev}
          , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
          , "init_db_to_90p_loaded": "true"
          , "evict_cached_data": "true"
          , "memory_limit_in_mb": 2.0 * 1024
          , "migrate_sstables": "true"
          , "monitor_temp": "true"
          , "workload_start_from": 0.899
          , "workload_stop_at":    -1.0
          , "simulation_time_dur_in_sec": 60000
          , "cache_filter_index_at_all_levels": "false"
          , "sst_migration_temperature_threshold": mt
          }
      params["rocksdb-quizup-runs"].append(dict(p1))
    #Cons.P(pprint.pformat(params))
    LaunchJob(params)


def Job_TestServer():
  params = { \
      # us-east-1, which is where the S3 buckets for experiment are.
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      # RocksDB can use the same AMI
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      , "block_storage_devs": []
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }
  LaunchJob(params)


def Job_QuizupMutantStorageSizeByTime():
  params = { \
      # us-east-1, which is where the S3 buckets for experiment are.
      "region": "us-east-1"
      , "inst_type": "c3.2xlarge"
      , "spot_req_max_price": 1.0
      # RocksDB can use the same AMI
      , "init_script": "mutant-cassandra-server-dev"
      , "ami_name": "mutant-cassandra-server"
      # 100 GB is good enough. 300 baseline IOPS. 2,000 burst IOPS. 3T sc1 has only 36 IOPS.
      , "block_storage_devs": [{"VolumeType": "gp2", "VolumeSize": 100, "DeviceName": "d"}]
      , "unzip_quizup_data": "true"
      , "run_cassandra_server": "false"
      # For now, it doesn't do much other than checking out the code and building.
      , "rocksdb": { }
      , "rocksdb-quizup-runs": []
      , "terminate_inst_when_done": "true"
      }
  p1 = { \
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
      , "slow_dev_paths": {"t1": "/mnt/ebs-gp2/rocksdb-data-quizup-t1"}
      , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
      , "init_db_to_90p_loaded": "false"
      , "evict_cached_data": "true"
      , "memory_limit_in_mb": 2.0 * 1024

      , "monitor_temp": "true"
      , "workload_start_from": -1.0
      , "workload_stop_at":    -1.0
      , "simulation_time_dur_in_sec": 60000
      , "sst_migration_temperature_threshold": 10
      }
  params["rocksdb-quizup-runs"].append(dict(p1))
  LaunchJob(params)


def Job_QuizupUnmodifiedRocksDBLatencyByMemorySizes():
  class Conf:
    exp_per_ec2inst = 8
    def __init__(self, stg_dev):
      self.stg_dev = stg_dev
      self.mem_sizes = []
    def Full(self):
      return (len(self.mem_sizes) >= Conf.exp_per_ec2inst)
    def Add(self, mem_size, force=False):
      if False:
        # Experiment already done
        if not force:
          if ((self.stg_dev == "local-ssd1") and (mem_size in [3.8, 3.6, 3.4, 3.2])) \
              or ((self.stg_dev == "ebs-gp2") and (mem_size in [4.2])):
                return
      self.mem_sizes.append(mem_size)
    def Size(self):
      return len(self.mem_sizes)
    def __repr__(self):
      return "(%s, %s)" % (self.stg_dev, self.mem_sizes)

  # The lower bound without getting the system overloaded are different for
  # different storage devices.  local-ssd1 and ebs-gp2 have 14, which is 1.4GB,
  # which the range() function sets the lower bound as 12. They are capped by
  # the main memory. OOM killer.  ebs-st1 can go 1.6GB without the storage
  # device overloaded, ebs-sc1 2.0GB.
  num_exp_per_conf = 5
  confs = []
  for stg_dev in ["local-ssd1", "ebs-gp2"]:
    conf = Conf(stg_dev)
    for j in range(num_exp_per_conf):
      for i in range(30, 12, -2):
        if conf.Full():
          confs.append(conf)
          conf = Conf(stg_dev)
        conf.Add(i/10.0)
    if conf.Size() > 0:
      confs.append(conf)

  stg_dev = "ebs-st1"
  conf = Conf(stg_dev)
  for j in range(num_exp_per_conf):
    for i in range(30, 14, -2):
      if conf.Full():
        confs.append(conf)
        conf = Conf(stg_dev)
      conf.Add(i/10.0)
  if conf.Size() > 0:
    confs.append(conf)

  stg_dev = "ebs-sc1"
  conf = Conf(stg_dev)
  for j in range(num_exp_per_conf):
    for i in range(30, 18, -2):
      if conf.Full():
        confs.append(conf)
        conf = Conf(stg_dev)
      conf.Add(i/10.0)
  if conf.Size() > 0:
    confs.append(conf)

  # Patch a missed experiment
  #confs[18].mem_sizes = confs[18].mem_sizes[4:]
  #confs = confs[18:19]

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))
  #sys.exit(0)

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-cassandra-server"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.stg_dev == "local-ssd1":
      pass
    elif conf.stg_dev == "ebs-gp2":
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"})
    elif conf.stg_dev == "ebs-st1":
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif conf.stg_dev == "ebs-sc1":
      params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
    else:
      raise RuntimeError("Unexpected")

    p1 = { \
        "exp_desc": inspect.currentframe().f_code.co_name[4:]
        , "fast_dev_path": "/mnt/%s/rocksdb-data" % conf.stg_dev
        , "db_path": "/mnt/%s/rocksdb-data/quizup" % conf.stg_dev
        , "init_db_to_90p_loaded": "true"
        , "evict_cached_data": "true"
        , "memory_limit_in_mb": 1024 * 3

        , "monitor_temp": "false"
        , "workload_start_from": 0.899
        , "workload_stop_at":    -1.0
        , "simulation_time_dur_in_sec": 60000
        }
    for ms in conf.mem_sizes:
      p1["memory_limit_in_mb"] = 1024.0 * ms
      params["rocksdb-quizup-runs"].append(dict(p1))
    LaunchJob(params)





# def Job_UnmodifiedLatencyByMemorySizesJason():
#   class Conf:
#     exp_per_ec2inst = 2
#     def __init__(self, stg_dev):
#       self.stg_dev = stg_dev
#       self.mem_sizes = []
#     def Full(self):
#       return (len(self.mem_sizes) >= Conf.exp_per_ec2inst)
#     def Add(self, mem_size, force=False):
#       self.mem_sizes.append(mem_size)
#     def Size(self):
#       return len(self.mem_sizes)
#     def __repr__(self):
#       return "(%s, %s)" % (self.stg_dev, self.mem_sizes)

#   # The lower bound without getting the system overloaded are different for
#   # different storage devices.  local-ssd1 and ebs-gp2 have 14, which is 1.4GB,
#   # which the range() function sets the lower bound as 12. They are capped by
#   # the main memory. OOM killer.  ebs-st1 can go 1.6GB without the storage
#   # device overloaded, ebs-sc1 2.0GB.
#   num_exp_per_conf = 4
#   confs = []
#   for stg_dev in ["local-ssd1", "ebs-gp2"]:
#     conf = Conf(stg_dev)
#     for j in range(num_exp_per_conf):
#       for i in range(30, 12, -2):
#         if conf.Full():
#           confs.append(conf)
#           conf = Conf(stg_dev)
#         conf.Add(i/10.0)
#     if conf.Size() > 0:
#       confs.append(conf)

#   stg_dev = "ebs-st1"
#   conf = Conf(stg_dev)
#   for j in range(num_exp_per_conf):
#     for i in range(30, 14, -2):
#       if conf.Full():
#         confs.append(conf)
#         conf = Conf(stg_dev)
#       conf.Add(i/10.0)
#   if conf.Size() > 0:
#     confs.append(conf)

#   stg_dev = "ebs-sc1"
#   conf = Conf(stg_dev)
#   for j in range(num_exp_per_conf):
#     for i in range(30, 18, -2):
#       if conf.Full():
#         confs.append(conf)
#         conf = Conf(stg_dev)
#       conf.Add(i/10.0)
#   if conf.Size() > 0:
#     confs.append(conf)

#   # Patch a missed experiment
#   #confs[18].mem_sizes = confs[18].mem_sizes[4:]
#   #confs = confs[18:19]

#   Cons.P("%d machines" % len(confs))
#   Cons.P(pprint.pformat(confs, width=100))
#   #sys.exit(0)

#   for conf in confs:
#     params = { \
#         # us-east-1, which is where the S3 buckets for experiment are.
#         "region": "us-east-1"
#         , "inst_type": "c3.2xlarge"
#         , "spot_req_max_price": 1.0
#         # RocksDB can use the same AMI
#         , "init_script": "mutant-cassandra-server-dev"
#         , "ami_name": "mutant-cassandra-server"
#         , "block_storage_devs": []
#         , "unzip_quizup_data": "true"
#         , "run_cassandra_server": "false"
#         # For now, it doesn't do much other than checking out the code and building.
#         , "rocksdb": { }
#         , "rocksdb-quizup-runs": []
#         , "terminate_inst_when_done": "true"
#         }
#     if conf.stg_dev == "local-ssd1":
#       pass
#     elif conf.stg_dev == "ebs-gp2":
#       params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"})
#     elif conf.stg_dev == "ebs-st1":
#       params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
#     elif conf.stg_dev == "ebs-sc1":
#       params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
#     else:
#       raise RuntimeError("Unexpected")

#     p1 = { \
#         "exp_desc": inspect.currentframe().f_code.co_name[4:]
#         , "fast_dev_path": "/mnt/%s/rocksdb-data" % conf.stg_dev
#         , "db_path": "/mnt/%s/rocksdb-data/quizup" % conf.stg_dev
#         , "init_db_to_90p_loaded": "true"
#         , "evict_cached_data": "true"
#         , "memory_limit_in_mb": 1024 * 3

#         , "monitor_temp": "false"
#         , "workload_start_from": 0.899
#         , "workload_stop_at":    -1.0
#         , "simulation_time_dur_in_sec": 60000
#         }
#     for ms in conf.mem_sizes:
#       p1["memory_limit_in_mb"] = 1024.0 * ms
#       params["rocksdb-quizup-runs"].append(dict(p1))
#     LaunchJob(params)


def Job_MutantLatencyByMemorySizesJason():
  class Conf:
    exp_per_ec2inst = 4
    def __init__(self, slow_dev):
      self.slow_dev = slow_dev
      self.mem_sizes = []
    def Full(self):
      return (len(self.mem_sizes) >= Conf.exp_per_ec2inst)
    def Add(self, mem_size, force=False):
      self.mem_sizes.append(mem_size)
    def Size(self):
      return len(self.mem_sizes)
    def __repr__(self):
      return "(%s, %s)" % (self.slow_dev, self.mem_sizes)

  # The lower bound without getting the system overloaded are different for
  # different storage devices.  local-ssd1 and ebs-gp2 have 14, which is 1.4GB,
  # which the range() function sets the lower bound as 12. They are capped by
  # the main memory. OOM killer.  ebs-st1 can go 1.6GB without the storage
  # device overloaded, ebs-sc1 2.0GB.
  num_exp_per_conf = 1
  BASE_MEMORY_SIZE = 2.3 
  confs = []
  for slow_dev in ["ebs-gp2", "ebs-st1", "ebs-sc1"]:
    conf = Conf(slow_dev)
    for j in range(num_exp_per_conf):
      # when record size is 1KB, the data size is 2.3GB, so 
      # we set size to 2.3*2, 2.3*.1.5, 2.3*1.2, 2.3, 2.3*0.9, 2.3*0.8, 2.3*0.7, 2.3*0.6, 2.3*0.5   
      # for i in [2, 1.5, 1.2, 1, 0.9, 0.8, 0.7, 0.6, 0.5]:
      for i in [2, 1, 0.6]:
        if conf.Full():
          confs.append(conf)
          conf = Conf(slow_dev)
        conf.Add(i*BASE_MEMORY_SIZE)
    if conf.Size() > 0:
      confs.append(conf)


  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))
  #sys.exit(0)

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-rocksDB-1a1a11a"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.slow_dev == "local-ssd1":
      pass
    elif conf.slow_dev == "ebs-gp2":
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"})
    elif conf.slow_dev == "ebs-st1":
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif conf.slow_dev == "ebs-sc1":
      params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
    else:
      raise RuntimeError("Unexpected")

    p1 = { \
        "exp_desc": "this is the mutant memSize experiments %s" %inspect.currentframe().f_code.co_name[4:]
        , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
        , "slow_dev_paths": {"t1": "/mnt/%s/rocksdb-data-quizup-t1" % conf.slow_dev}
        , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
        , "init_db_to_90p_loaded": "true"
        , "evict_cached_data": "true"
        , "memory_limit_in_mb": 2.0 * 1024
        , "migrate_sstables": "true"
        , "monitor_temp": "true"
        , "workload_start_from": 0.899
        , "workload_stop_at":    -1.0
        , "simulation_time_dur_in_sec": 60000
        , "cache_filter_index_at_all_levels": "false"
        , "sst_migration_temperature_threshold": 4
        }

    for ms in conf.mem_sizes:
      p1["memory_limit_in_mb"] = 1024.0 * ms
      params["rocksdb-quizup-runs"].append(dict(p1))
    LaunchJob(params)



def Job_MutantLatencyByRecordSizesJason():
  RECORD_SIZES = [1, 2, 4, 6, 8, 16, 32, 64, 128]
  RECORD_SIZES = [1, 2, 4, 8]

  class Conf:
    exp_per_ec2inst = 1
    def __init__(self, stg_dev):
      self.stg_dev = stg_dev
      self.record_sizes = []
    def Full(self):
      return (len(self.record_sizes) >= Conf.exp_per_ec2inst)
    def Add(self, mem_size, force=False):
      self.record_sizes.append(mem_size)
    def Size(self):
      return len(self.record_sizes)
    def __repr__(self):
      return "(%s, %s)" % (self.stg_dev, self.record_sizes)

  # The lower bound without getting the system overloaded are different for
  # different storage devices.  local-ssd1 and ebs-gp2 have 14, which is 1.4GB,
  # which the range() function sets the lower bound as 12. They are capped by
  # the main memory. OOM killer.  ebs-st1 can go 1.6GB without the storage
  # device overloaded, ebs-sc1 2.0GB.
  num_exp_per_conf = 1
  confs = []
  for stg_dev in ["ebs-gp2", "ebs-st1", "ebs-sc1"]:
    conf = Conf(stg_dev)
    for j in range(num_exp_per_conf):
      for i in RECORD_SIZES:
        if conf.Full():
          confs.append(conf)
          conf = Conf(stg_dev)
        conf.Add(i*1000)
    if conf.Size() > 0:
      confs.append(conf)


  # Patch a missed experiment
  #confs[18].mem_sizes = confs[18].mem_sizes[4:]
  #confs = confs[18:19]

  Cons.P("%d machines" % len(confs))
  Cons.P(pprint.pformat(confs, width=100))
  #sys.exit(0)

  for conf in confs:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        # RocksDB can use the same AMI
        , "init_script": "mutant-cassandra-server-dev"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "unzip_quizup_data": "true"
        , "run_cassandra_server": "false"
        # For now, it doesn't do much other than checking out the code and building.
        , "rocksdb": { }
        , "rocksdb-quizup-runs": []
        , "terminate_inst_when_done": "true"
        }
    if conf.stg_dev == "local-ssd1":
      pass
    elif conf.stg_dev == "ebs-gp2":
      params["block_storage_devs"].append({"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"})
    elif conf.stg_dev == "ebs-st1":
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif conf.stg_dev == "ebs-sc1":
      params["block_storage_devs"].append({"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"})
    else:
      raise RuntimeError("Unexpected")

    p1 = { \
        "exp_desc": inspect.currentframe().f_code.co_name[4:]
        , "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
        , "slow_dev_paths": {"t1": "/mnt/%s/rocksdb-data-quizup-t1" % conf.stg_dev}
        , "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
        , "init_db_to_90p_loaded": "true"
        , "evict_cached_data": "true"
        , "memory_limit_in_mb": 2.0 * 1024
        , "migrate_sstables": "true"
        , "monitor_temp": "true"
        , "workload_start_from": 0.899
        , "workload_stop_at":    -1.0
        , "simulation_time_dur_in_sec": 60000
        , "cache_filter_index_at_all_levels": "false"
        , "sst_migration_temperature_threshold": 4
        , "record_size": 1
        }

    for rs in conf.record_sizes:
      p1["record_size"] = rs 
      params["rocksdb-quizup-runs"].append(dict(p1))
    LaunchJob(params)



def Job_Ycsb_Test():
  # Job conf per EC2 inst
  class ConfEc2Inst:
    exp_per_ec2inst = 1

    def __init__(self):
      self.params = []
    def Full(self):
      return (len(self.params) >= ConfEc2Inst.exp_per_ec2inst)
    def Add(self, params):
      self.params.append(params)
    def Size(self):
      return len(self.params)
    def __repr__(self):
      return "%s" % (self.params)

  workload_type = "a"

  db_stg_dev = "ebs-st1"
  #db_stg_dev = "local-ssd1"

  if db_stg_dev == "local-ssd1":
    target_iops_range = [20000]
  elif db_stg_dev == "ebs-st1":
    target_iops_range = [800]
  random.shuffle(target_iops_range)

  confs_ec2 = []
  conf_ec2 = ConfEc2Inst()
  for i in range(1):
    for ti in target_iops_range:
      if conf_ec2.Full():
        confs_ec2.append(conf_ec2)
        conf_ec2 = ConfEc2Inst()
      conf_ec2.Add(ti)
  if conf_ec2.Size() > 0:
    confs_ec2.append(conf_ec2)

  Cons.P("%d machine(s)" % len(confs_ec2))
  Cons.P(pprint.pformat(confs_ec2, width=100))

  for conf_ec2 in confs_ec2:
    params = { \
        # us-east-1, which is where the S3 buckets for experiment are.
        "region": "us-east-1"
        , "inst_type": "c3.2xlarge"
        , "spot_req_max_price": 1.0
        , "init_script": "mutant-rocksdb"
        , "ami_name": "mutant-rocksdb"
        , "block_storage_devs": []
        , "ec2_tag_Name": inspect.currentframe().f_code.co_name[4:]
        # Initialize local SSD by erasing. Some EC2 instance types need this.
        , "erase_local_ssd": "true"
        , "unzip_quizup_data": "false"
        , "run_cassandra_server": "false"
        , "rocksdb": {}  # This doesn't do much other than checking out the code and building.
        , "rocksdb-quizup-runs": []
        , "ycsb-runs": []
        , "terminate_inst_when_done": "true"
        }
    if db_stg_dev == "ebs-st1":
      # 40 MiB/s/TiB. With 3 TiB, 120 MiB/sec.
      params["block_storage_devs"].append({"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"})
    elif db_stg_dev == "local-ssd1":
      pass
    else:
      raise RuntimeError("Unexpected")

    ycsb_runs = {
      "exp_desc": inspect.currentframe().f_code.co_name[4:]
      , "workload_type": workload_type
      , "db_path": "/mnt/%s/rocksdb-data/ycsb" % db_stg_dev
      , "db_stg_dev_paths": [
          "/mnt/%s/rocksdb-data/ycsb/t0" % db_stg_dev]
      , "runs": []
      }

    for target_iops in conf_ec2.params:
      op_cnt = 10000000 / 2
      if target_iops < 10000:
        op_cnt = op_cnt / 10
      ycsb_runs["runs"].append({
        # The load phase needs to be slow. Otherwise, the SSTables get too big. Probably because of the pending compactions,
        #   which will affect the performance of in the run phase.
        #   However, with a slow loading like with -target 10000, it takes 16 mins.
        # Decided to keep the DB image in S3. Takes about 1 min to sync.
        "load": {
          #"use_preloaded_db": ""
          # This can be used for any devices. Now the name is misleading, but ok.
          "use_preloaded_db": "ycsb-%s-10M-records-rocksdb" % workload_type
          , "ycsb_params": " -p recordcount=10000000 -target 10000"
          }
        # How long it takes when the system gets saturated.
        #   Without memory throttling, 10M reqs: 101 sec.
        #                              30M reqs: 248 sec
        #   With a 4GB memory throttling, 10M reqs: 119 sec. Not a lot of difference. Hmm.
        #                                 30M reqs: 305 sec. Okay.
        #
        # 11G of data. With 5GB, JVM seems to be doing just fine.
        # Out of the 30M operations, 0.95 of them are reads; 0.05 are writes.
        #   With the raw latency logging, YCSB hogs more memory: it keeps the data in memory.
        , "run": {
          "evict_cached_data": "true"
          , "memory_limit_in_mb": 5.0 * 1024
          # Mutant doesn't trigger any of these by default: it behaves like unmodified RocksDB.
          , "ycsb_params": " -p recordcount=10000000 -p operationcount=%s -p readproportion=0.95 -p insertproportion=0.05 -target %d" % (op_cnt, target_iops)
          }
        , "mutant_options": {
          "monitor_temp": "false"
          , "migrate_sstables": "false"
          , "sst_ott": 0
          , "cache_filter_index_at_all_levels": "false"
          # Replaying a workload in the past
          #, "replaying": {
          #  "simulated_time_dur_sec": 1365709.587
          #  , "simulation_time_dur_sec": 60000
          #  }
          , "db_stg_dev_paths": ycsb_runs["db_stg_dev_paths"]
          }
        })

    params["ycsb-runs"] = dict(ycsb_runs)
    LaunchJob(params)






def LaunchJob(params):
  # Spot instance
  ReqSpotInsts.Req(params)

  # On-demand instance
  #LaunchOnDemandInsts.Launch(params)


if __name__ == "__main__":
  sys.exit(main(sys.argv))











  
