节点的part数量一致卡住
```bash
TENCENT64 :) select table, partition,count(*) as cnt from system.parts where active=1 group by table,partition  order by cnt desc limit 10;

SELECT
    table,
    partition,
    count(*) AS cnt
FROM system.parts
WHERE active = 1
GROUP BY
    table,
    partition
ORDER BY cnt DESC
LIMIT 10

Query id: cdaebfe8-9f58-4e38-969f-25e7f6c6c7b9

┌─table────────────────────────────────────────────────────────────────────────────────────────────────────┬─partition───────────┬─cnt─┐
│ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 2021-11-14 00:00:00 │  43 │
│ query_log                                                                                                │ 202111              │  17 │
│ 1251316161_SPPD_taf_ts-60_local                                                                          │ 2021-11-09 00:00:00 │  16 │
│ 1251316161_ccmgrowth_rta_calc_cover_local                                                                │ 2021-11-14 00:00:00 │  15 │
│ 1258344699_InstantMessage_imsdk_quality_c2c_latency_1s-60_local                                          │ 2021-11-14 00:00:00 │  15 │
│ 1258344699_InstantMessage_imsdk_event_login_total_local                                                  │ 2021-10-30 00:00:00 │  15 │
│ 1258344699_InstantMessage_imsdk_event_login_cost_time_local                                              │ 2021-10-30 00:00:00 │  14 │
│ 1251316161_tencent-doctor_http_request_beego-60_local                                                    │ 2021-11-14 00:00:00 │  14 │
│ 1258344699_InstantMessage_imsdk_quality_c2c_latency_1s_local                                             │ 2021-11-14 00:00:00 │  14 │
│ 1251316161_medicalbaike_client_handled_cost-60_local                                                     │ 2021-11-14 00:00:00 │  14 │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┴─────────────────────┴─────┘

10 rows in set. Elapsed: 0.051 sec. Processed 15.95 thousand rows, 1.66 MB (313.76 thousand rows/s., 32.69 MB/s.) 
```
检查replication_queue 
```bash
TENCENT64 :) select * from system.replication_queue where table='1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local' limit 5;

SELECT *
FROM system.replication_queue
WHERE table = '1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local'
LIMIT 5

Query id: d4655d21-6d29-4614-88a5-fd26a435b1ff

┌─database──────┬─table────────────────────────────────────────────────────────────────────────────────────────────────────┬─replica_name─┬─position─┬─node_name────────┬─type────────┬─────────create_time─┬─required_quorum─┬─source_replica─┬─new_part_name──────────┬─parts_to_merge──────────────────────────────────────┬─is_detach─┬─is_currently_executing─┬─num_tries─┬─last_exception─┬───last_attempt_time─┬─num_postponed─┬─postpone_reason────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──last_postpone_time─┬─merge_type─┐
│ cloud_monitor │ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 1            │        0 │ queue-0000375227 │ MERGE_PARTS │ 2021-11-15 14:03:58 │               0 │ 2              │ 1636819200_0_4582_3957 │ ['1636819200_0_4581_3956','1636819200_4582_4582_0'] │         0 │                      0 │      6475 │                │ 2021-11-18 18:28:45 │        239031 │ Not executing log entry queue-0000375227 for part 1636819200_0_4582_3957 because it is covered by part 1636819200_0_4619_3994 that is currently executing. │ 2021-11-18 18:28:48 │ REGULAR    │
│ cloud_monitor │ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 1            │        1 │ queue-0000375233 │ MERGE_PARTS │ 2021-11-15 14:04:53 │               0 │ 2              │ 1636819200_0_4585_3960 │ ['1636819200_0_4584_3959','1636819200_4585_4585_0'] │         0 │                      0 │      6515 │                │ 2021-11-18 18:28:45 │        234247 │ Not executing log entry queue-0000375233 for part 1636819200_0_4585_3960 because it is covered by part 1636819200_0_4619_3994 that is currently executing. │ 2021-11-18 18:28:48 │ REGULAR    │
│ cloud_monitor │ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 1            │        2 │ queue-0000375239 │ MERGE_PARTS │ 2021-11-15 14:06:53 │               0 │ 2              │ 1636819200_0_4588_3963 │ ['1636819200_0_4587_3962','1636819200_4588_4588_0'] │         0 │                      0 │      6534 │                │ 2021-11-18 18:28:45 │        231123 │ Not executing log entry queue-0000375239 for part 1636819200_0_4588_3963 because it is covered by part 1636819200_0_4619_3994 that is currently executing. │ 2021-11-18 18:28:48 │ REGULAR    │
│ cloud_monitor │ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 1            │        3 │ queue-0000375245 │ MERGE_PARTS │ 2021-11-15 14:08:00 │               0 │ 2              │ 1636819200_0_4591_3966 │ ['1636819200_0_4590_3965','1636819200_4591_4591_0'] │         0 │                      0 │      6588 │                │ 2021-11-18 18:28:45 │        225039 │ Not executing log entry queue-0000375245 for part 1636819200_0_4591_3966 because it is covered by part 1636819200_0_4619_3994 that is currently executing. │ 2021-11-18 18:28:48 │ REGULAR    │
│ cloud_monitor │ 1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local │ 1            │        4 │ queue-0000375253 │ MERGE_PARTS │ 2021-11-15 14:10:00 │               0 │ 2              │ 1636819200_0_4595_3970 │ ['1636819200_0_4594_3969','1636819200_4595_4595_0'] │         0 │                      0 │      6727 │                │ 2021-11-18 18:28:45 │        218722 │ Not executing log entry queue-0000375253 for part 1636819200_0_4595_3970 because it is covered by part 1636819200_0_4619_3994 that is currently executing. │ 2021-11-18 18:28:48 │ REGULAR    │
└───────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────────────┴──────────┴──────────────────┴─────────────┴─────────────────────┴─────────────────┴────────────────┴────────────────────────┴─────────────────────────────────────────────────────┴───────────┴────────────────────────┴───────────┴────────────────┴─────────────────────┴───────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴─────────────────────┴────────────┘

5 rows in set. Elapsed: 0.014 sec. 
```
可以看到有 GET_PART 与 MERGE_PARTS 死锁的情况。
通过 
```bash
DETACH TABLE xxxx

deleteall /clickhouse/tables/1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local/2/replicas/1/queue

create /clickhouse/tables/1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local/2/replicas/1/queue

ATTACH TABLE xxx
```
再检查发现已经恢复
```bash
select * from system.replication_queue where table='1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local' limit 5;

SELECT *
FROM system.replication_queue
WHERE table = '1251316161_tencent-doctor_TencentDoctor_HttpWenzhenOpenServer_set_doctor_end_conversation_count-60_local'
LIMIT 5

Query id: d265d091-b9ef-448a-b277-dc55f8f0e664

Ok.

0 rows in set. Elapsed: 0.018 sec. 

TENCENT64 :) select table, partition,count(*) as cnt from system.parts where active=1 group by table,partition  order by cnt desc limit 10;

SELECT
    table,
    partition,
    count(*) AS cnt
FROM system.parts
WHERE active = 1
GROUP BY
    table,
    partition
ORDER BY cnt DESC
LIMIT 10

Query id: 2c52d697-107b-44b9-86bc-d1952c1a039b

┌─table───────────────────────────────────────────────────────────┬─partition───────────┬─cnt─┐
│ query_thread_log                                                │ 202111              │  17 │
│ 1251316161_medicalbaike_client_handled_cost-60_local            │ 2021-11-14 00:00:00 │  17 │
│ 1251316161_SPPD_taf_ts-60_local                                 │ 2021-11-14 00:00:00 │  16 │
│ 1251316161_SPPD_taf_ts-60_local                                 │ 2021-11-09 00:00:00 │  16 │
│ 1258344699_InstantMessage_imsdk_quality_c2c_latency_1s-60_local │ 2021-11-14 00:00:00 │  15 │
│ 1258344699_InstantMessage_imsdk_event_login_total_local         │ 2021-10-30 00:00:00 │  15 │
│ 1251316161_ccmgrowth_rta_calc_cover_local                       │ 2021-10-30 00:00:00 │  14 │
│ 1258344699_InstantMessage_imsdk_event_login_cost_time_local     │ 2021-10-30 00:00:00 │  14 │
│ 1300543852_tcg_tcg_cg_client_stat-60_local                      │ 2021-11-14 00:00:00 │  14 │
│ 1251316161_ccmgrowth_rta_calc_cover-60_local                    │ 2021-11-14 00:00:00 │  13 │
└─────────────────────────────────────────────────────────────────┴─────────────────────┴─────┘

10 rows in set. Elapsed: 0.058 sec. Processed 15.84 thousand rows, 1.65 MB (271.55 thousand rows/s., 28.31 MB/s.) 
```