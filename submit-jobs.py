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


<<<<<<< HEAD
# Get the queue. Create one if not exists.
_sqs = None
_sqs_q = None
def _GetQ():
	global _sqs
	if _sqs is None:
		_sqs = boto3.resource("sqs", region_name = JobReq.sqs_region)

	global _sqs_q
	if _sqs_q is None:
		_sqs_q = _sqs.get_queue_by_name(
				QueueName = JobReq.sqs_q_name,
				# QueueOwnerAWSAccountId='string'
				)
		#Cons.P(pprint.pformat(vars(_sqs_q), indent=2))
		#{ '_url': 'https://queue.amazonaws.com/998754746880/mutant-exps',
		#		  'meta': ResourceMeta('sqs', identifiers=[u'url'])}
	return _sqs_q


def Job_MutantDevS1C1():
	_EnqReq(
			{
				# The server and the client are in the same AZ.
				"region": "us-east-1"

				# Client uses the same instance type as the server, cause it generates
				# all requests for a cluster of servers.
				#
				#            vCPU ECU Memory (GiB) Instance Storage (GB) Linux/UNIX Usage
				# c3.2xlarge    8  28           15            2 x 80 SSD  $0.42  per Hour.
				# r3.xlarge     4  13         30.5            1 x 80 SSD  $0.333 per Hour
				#
				# r3 types don't need local SSD initialization. However, even after
				# init, it's still slower(86 MB/s) than c3 (372 MB/s).
				#
				# c3.2xlarge is a better fit for Cassandra with the YCSB "read latest"
				# workload. The workload is quite computation heavy.
				#
				# When "spot_req" is not specified, the job controller launches
				# on-demand instances.
				#
				#, "spot_req": {"max_price": 2.0}
				, "inst_type": "c3.2xlarge"

				, "server": {
					# Note: We'll see if the AMIs need to be separated by DBs.
					"init_script": "mutant-cassandra-server-dev"
					, "ami_name": "mutant-cassandra-server"
					, "num_nodes": "1"

					# The storage cost is higher than the VM spot price, which is around
					# $0.1/hour. You will want to be careful.
					#                             $/GB-month     $/hour
					#                                 size_in_GB
					#   EBS gp2                        0.100  80 0.0110
					#   EBS st1 (throughput optimized) 0.045 500 0.0308
					#   EBS sc1 (cold HDD)             0.025 500 0.0171
					#
					#   calc "0.100 *  80 / (365.25/12*24)"
					#   calc "0.045 * 500 / (365.25/12*24)"
					#   calc "0.025 * 500 / (365.25/12*24)"
					#
					# For st1 and sc1, 500 GB is the minimum size.
					, "block_storage_devs": [
						{"VolumeType": "gp2", "VolumeSize": 80, "DeviceName": "d"}
						#, {"VolumeType": "st1", "VolumeSize": 500, "DeviceName": "e"}
						#, {"VolumeType": "sc1", "VolumeSize": 500, "DeviceName": "f"}
						]

					# Pre-populate DB using the 50GB one stored in S3.
					, "pre_populate_db": "true"
					}

				, "client" : {
					"init_script": "mutant-cassandra-client-dev"
					, "ami_name": "mutant-client"
					, "ycsb": YcsbWorkload.A()
					, "terminate_cluster_when_done": "false"
					}
				}
			)


def Job_MutantDevS1():
	_EnqReq(
			{"region": "us-east-1"
				, "inst_type": "c3.2xlarge"

				, "server": {
					# RocksDB can use the same AMI
					"init_script": "mutant-cassandra-server-dev"
					, "ami_name": "mutant-cassandra-server"
					, "num_nodes": "1"
					, "block_storage_devs": [
						{"VolumeType": "gp2", "VolumeSize": 80, "DeviceName": "d"}

						# 1TB gp2 for 3000 IOPS
						#{"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"}

						# 1TB st1 for 40 Mib/s, 250 Mib/s (burst) throughput. Good enough
						# for running the 100% quizup data for 5400 secs.

						# Try 3TB. 1TB st1 had higher latency than the 3TB sc1! Unfair.
						#{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}

						# 3TB. 36 Mib/s, 240 Mib/s
						#{"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"}
						]
					, "unzip_quizup_data": "true"

					, "run_cassandra_server": "false"

					# For now, it doesn't do much other than checking out the code and building.
					, "rocksdb": { }
					# quizup workload generator

					# Storage usage measurement for unmodified RocksDB and Mutant with
					# sstable migration threshold 10.
					#, "rocksdb-quizup": RocksDBQuizup.storage_usage_measurement_unmodified_rocksdb
					, "rocksdb-quizup": RocksDBQuizup.storage_usage_measurement_mutant
					}
				}
			)


def Job_MutantLatencyBySstMigTempThresholds():
	for sst_mig_temp_th in [200, 150, 100, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1]:
		_EnqReq(
				{"region": "us-east-1"
					, "inst_type": "c3.2xlarge"

					, "server": {
						# RocksDB can use the same AMI
						"init_script": "mutant-cassandra-server-dev"
						, "ami_name": "mutant-cassandra-server"
						, "num_nodes": "1"
						, "block_storage_devs": [
							# 1TB gp2 for 3000 IOPS
							#{"VolumeType": "gp2", "VolumeSize": 1000, "DeviceName": "d"}

							# 3TB st1 for 120 Mib/s, 500 Mib/s (burst) throughput.
							#   http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EBSVolumeTypes.html
							{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}

							# 3TB sc1 for 36 Mib/s, 240 Mib/s (burst).
							#{"VolumeType": "sc1", "VolumeSize": 3000, "DeviceName": "f"}
							]
						, "unzip_quizup_data": "true"

						, "run_cassandra_server": "false"

						# For now, it doesn't do much other than checking out the code and building.
						, "rocksdb": { }

						, "rocksdb-quizup": {
							"mutant_enabled": "true"
							, "sst_migration_temperature_threshold": sst_mig_temp_th
							, "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
							#, "slow_dev_paths": {"t1": "/mnt/ebs-gp2/rocksdb-data-quizup-t1"}
							, "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
							#, "slow_dev_paths": {"t1": "/mnt/ebs-sc1/rocksdb-data-quizup-t1"}
							, "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
							, "init_db_to_90p_loaded": "true"
							, "evict_cached_data": "true"
							, "workload_start_from": 0.899
							, "workload_stop_at":    -1.0
							, "simulation_time_dur_in_sec": 60000
							, "terminate_inst_when_done": "true"
							}
						}
					}
				)


def Job_Castnet():
	_EnqReq(
			{"region": "us-east-1"
				# Client uses the same instance type as the server, cause it generates
				# all requests for a cluster of servers.
				#, "spot_req": {"inst_type": "c3.2xlarge", "max_price": 2.0}
				#            vCPU ECU Memory (GiB) Instance Storage (GB) Linux/UNIX Usage
				# c3.2xlarge    8  28           15            2 x 80 SSD   $0.42 per Hour

				, "spot_req": {"inst_type": "c3.8xlarge", "max_price": 8.0}
				#            vCPU ECU Memory (GiB) Instance Storage (GB) Linux/UNIX Usage
				# c3.2xlarge    8  28           15            2 x 80 SSD   $0.42 per Hour

				# The client needs to be in the same AZ.
				, "client" : {
					"init_script": "castnet-dev"
					# TODO: modify after moving some data
					, "ami_name": "castnet"
					}
				}
			)


def _EnqReq(attrs):
	with Cons.MT("Enq a request: "):
		# Need to make a copy so that an SQS message can be sent while attrs is being
		# modified.
		attrs = attrs.copy()
		Cons.P(pprint.pformat(attrs))

		# A Mutant job req has too many attributes - well over 10. Pack then with a
		# json format in the message body, not in the attributes.
		#
		# "You can attach up to ten attributes to each of your messages. The entire
		# message, including the body plus all names, types, and values, can be as
		# large as 256 KB (262,144 bytes)."
		# - https://aws.amazon.com/blogs/aws/simple-queue-service-message-attributes
		#
		# Seems like the msg body doesn't need to be based64 encoded.
		_GetQ().send_message(MessageBody=json.dumps(attrs))
=======
def Job_MutantLatencyBySstMigTempThresholds():
	params = { \
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
				{"VolumeType": "st1", "VolumeSize": 3000, "DeviceName": "e"}

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
			#, "sst_migration_temperature_threshold": sst_mig_temp_th
			, "fast_dev_path": "/mnt/local-ssd1/rocksdb-data"
			#, "slow_dev_paths": {"t1": "/mnt/ebs-gp2/rocksdb-data-quizup-t1"}
			, "slow_dev_paths": {"t1": "/mnt/ebs-st1/rocksdb-data-quizup-t1"}
			#, "slow_dev_paths": {"t1": "/mnt/ebs-sc1/rocksdb-data-quizup-t1"}
			, "db_path": "/mnt/local-ssd1/rocksdb-data/quizup"
			, "init_db_to_90p_loaded": "true"
			, "evict_cached_data": "true"
			, "workload_start_from": 0.899
			, "workload_stop_at":    -1.0
			, "simulation_time_dur_in_sec": 60000
			, "terminate_inst_when_done": "true"
			}

	for sst_mig_temp_th in [200, 150, 100, 50, 40]:
		params["rocksdb-quizup-runs"].append(dict(p1, "sst_migration_temperature_threshold"=sst_mig_temp_th)))
		LaunchOnDemandInsts.Launch(params)

	#for sst_mig_temp_th in [200, 150, 100, 50, 40, 30, 20, 15, 10, 5, 4, 3, 2, 1]:
>>>>>>> 78aee9127c99160afeb68755956a81844ce0af0f


if __name__ == "__main__":
	sys.exit(main(sys.argv))
