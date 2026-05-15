Compaction Trigger.
i) Level saturation: level size goes beyond a nominal threshold
ii) #Sorted runs: sorted run count for a level reaches a threshold
iii) File staleness: a file lives in a level for too long
iv) Space amplification (SA): overall SA surpasses a threshold
v) Tombstone-TTL: files have expired tombstone-TTL

Data layout. 