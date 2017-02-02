#!/usr/bin/env python

import boto3
import botocore
import json
import os
import pprint
import sys
import time
import types

sys.path.insert(0, "%s/lib/util" % os.path.dirname(__file__))
import Cons

sys.path.insert(0, "%s/lib" % os.path.dirname(__file__))
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
		Cons.P("  Jobs available: %s" % " ".join(job_list))
		sys.exit(1)

	job = "Job_" + argv[1]

	# http://stackoverflow.com/questions/3061/calling-a-function-of-a-module-from-a-string-with-the-functions-name-in-python
	globals()[job]()


def Job_UnmodifiedRocksDBLatencyByMemorySizes():
	class Conf:
		def __init__(self, stg_dev):
			self.stg_dev = stg_dev
			self.mem_sizes = []
		def Full(self):
			return (len(self.mem_sizes) >= 4)
		def Add(self, mem_size, force=False):
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

	confs = []
	if True:
		for stg_dev in ["local-ssd1", "ebs-gp2", "ebs-st1", "ebs-sc1"]:
			conf = Conf(stg_dev)
			for i in range(42, 8, -2):
				if conf.Full():
					confs.append(conf)
					conf = Conf(stg_dev)
				conf.Add(i/10.0)
			if conf.Size() > 0:
				confs.append(conf)
	else:
		# Manual setting
		conf = Conf("ebs-gp2")
		conf.Add(4.2, force=True)
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
				"exp_desc": "Unmodified RocksDB latency by different memory sizes"
				, "fast_dev_path": "/mnt/%s/rocksdb-data" % conf.stg_dev
				, "db_path": "/mnt/%s/rocksdb-data/quizup" % conf.stg_dev
				, "init_db_to_90p_loaded": "true"
				, "evict_cached_data": "true"
				, "memory_limit_in_mb": 1024 * 3

				, "mutant_enabled": "false"
				, "workload_start_from": 0.899
				, "workload_stop_at":    -1.0
				, "simulation_time_dur_in_sec": 60000
				}
		for ms in conf.mem_sizes:
			p1["memory_limit_in_mb"] = 1024.0 * ms
			params["rocksdb-quizup-runs"].append(dict(p1))
		LaunchJob(params)


def Job_MutantStorageUsage():
	params = { \
			# us-east-1, which is where the S3 buckets for experiment are.
			"region": "us-east-1"
			, "inst_type": "c3.2xlarge"

			# RocksDB can use the same AMI
			, "init_script": "mutant-cassandra-server-dev"
			, "ami_name": "mutant-cassandra-server"
			, "block_storage_devs": [
				{"VolumeType": "gp2", "VolumeSize": 100, "DeviceName": "d"}
				]
			, "unzip_quizup_data": "true"

			, "run_cassandra_server": "false"

			# For now, it doesn't do much other than checking out the code and building.
			, "rocksdb": { }

			, "rocksdb-quizup-runs": []
			}

	p1 = { \
			"mutant_enabled": "true"

			, "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
			, "slow_dev_paths": {"t1": "/mnt/ebs-gp2/rocksdb-data-quizup-t1"}

			, "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
			, "init_db_to_90p_loaded": "false"
			, "evict_cached_data": "true"
			, "workload_start_from": -1.0
			, "workload_stop_at":    -1.0
			, "simulation_time_dur_in_sec": 60000
			, "terminate_inst_when_done": "true"
			}

	params["rocksdb-quizup-runs"].append(dict(p1))
	LaunchJob(params)


def Job_UnmodifiedRocksDBLatency():
	params = { \
			# us-east-1, which is where the S3 buckets for experiment are.
			"region": "us-east-1"
			, "inst_type": "c3.2xlarge"

			# RocksDB can use the same AMI
			, "init_script": "mutant-cassandra-server-dev"
			, "ami_name": "mutant-cassandra-server"
			, "block_storage_devs": [
				# 1TB gp2 for 3000 IOPS
				#{"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"}

				# 3TB st1 for 120 Mib/s, 500 Mib/s (burst) throughput.
				#   http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html
				#{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}

				# 3TB sc1 for 36 Mib/s, 240 Mib/s (burst).
				{"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"}
				]
			, "unzip_quizup_data": "true"

			, "run_cassandra_server": "false"

			# For now, it doesn't do much other than checking out the code and building.
			, "rocksdb": { }

			, "rocksdb-quizup-runs": []
			}

	p1 = { \
			"mutant_enabled": "false"

			#, "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
			#, "fast_dev_path": "/mnt/ebs-gp2/rocksdb-data"
			#, "fast_dev_path": "/mnt/ebs-st1/rocksdb-data"
			, "fast_dev_path": "/mnt/ebs-sc1/rocksdb-data"

			, "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
			, "init_db_to_90p_loaded": "true"
			, "evict_cached_data": "true"
			, "workload_start_from": 0.899
			, "workload_stop_at":    -1.0
			, "simulation_time_dur_in_sec": 60000
			, "terminate_inst_when_done": "true"
			}

	for i in range(10):
		params["rocksdb-quizup-runs"].append(dict(p1))
	LaunchJob(params)


def Job_MutantLatencyBySstMigTempThresholds():
	params = { \
			# us-east-1, which is where the S3 buckets for experiment are.
			"region": "us-east-1"
			, "inst_type": "c3.2xlarge"

			# RocksDB can use the same AMI
			, "init_script": "mutant-cassandra-server-dev"
			, "ami_name": "mutant-cassandra-server"
			, "block_storage_devs": [
				# 1TB gp2 for 3000 IOPS
				{"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"}

				# 3TB st1 for 120 Mib/s, 500 Mib/s (burst) throughput.
				#   http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html
				#{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}

				# 3TB sc1 for 36 Mib/s, 240 Mib/s (burst).
				#{"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"}
				]
			, "unzip_quizup_data": "true"

			, "run_cassandra_server": "false"

			# For now, it doesn't do much other than checking out the code and building.
			, "rocksdb": { }

			, "rocksdb-quizup-runs": []
			}

	p1 = { \
			"mutant_enabled": "true"
			#, "sst_migration_temperature_threshold": 10
			, "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
			, "slow_dev_paths": {"t1": "/mnt/ebs-gp2/rocksdb-data-quizup-t1"}
			#, "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
			#, "slow_dev_paths": {"t1": "/mnt/ebs-sc1/rocksdb-data-quizup-t1"}
			, "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
			, "init_db_to_90p_loaded": "true"
			, "evict_cached_data": "true"
			, "workload_start_from": 0.899
			, "workload_stop_at":    -1.0
			, "simulation_time_dur_in_sec": 60000
			, "terminate_inst_when_done": "true"
			}

	for sst_mig_temp_th in [200, 150, 100, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1] * 2:
		p1["sst_migration_temperature_threshold"] = sst_mig_temp_th
		params["rocksdb-quizup-runs"].append(dict(p1))
	LaunchJob(params)


def LaunchJob(params):
	# Spot instance
	ReqSpotInsts.Req(params)

	# On-demand instance
	#LaunchOnDemandInsts.Launch(params)



if __name__ == "__main__":
	sys.exit(main(sys.argv))
