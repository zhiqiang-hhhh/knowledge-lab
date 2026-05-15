profile_content = '''-  ColumnCount:  1
                                      -  DeleteBitmapGetAggTime:  0ns
                                      -  MemoryUsage:  
                                          -  FreeBlocks:  3.68  MB
                                      -  NewlyCreateFreeBlocksNum:  472
                                      -  NumScaleUpScanners:  0
                                      -  ReaderInitTime:  16.149ms
                                      -  RowsDelFiltered:  0
                                      -  ScanNodeDeserializationBlockTime:  1.15ms
                                      -  ScannerBatchWaitTime:  0ns
                                      -  ScannerConvertBlockTime:  0ns
                                      -  ScannerCpuTime:  93.766ms
                                      -  ScannerCtxSchedTime:  1sec456ms
                                      -  ScannerFilterTime:  125.688us
                                      -  ScannerGetBlockTime:  210.426ms
                                      -  ScannerInitTime:  356.871us
                                      -  ScannerSchedCount:  48
                                      -  ScannerSerializationBlockTime:  1.588ms
                                      -  SerializedBinarySize:  3.93  MB'''

for i, line in enumerate(profile_content.splitlines()):
    line = line.strip()
    if line.startswith('-  ColumnCount:'):
        column_count = int(line.split(':')[-1].strip())
        print("ColumnCount: " + str(column_count))
    elif line.startswith('-  ScanNodeDeserializationBlockTime:'):
        scan_node_deserialization_block_time = float(line.split(':')[-1].strip()[:-2])  # Remove 'ms'
        print("ScanNodeDeserializationBlockTime: " + str(scan_node_deserialization_block_time) + " ms")
    elif line.startswith('-  ScannerSerializationBlockTime:'):
        scanner_serialization_block_time = float(line.split(':')[-1].strip()[:-2])  # Remove 'ms'
        print("ScannerSerializationBlockTime: " + str(scanner_serialization_block_time) + " ms")
    elif line.startswith('-  SerializedBinarySize:'):
        serialized_binary_size = float(line.split(':')[-1].strip().split()[0])  # Get the numeric value before 'MB'
        print("SerializedBinarySize: " + str(serialized_binary_size) + " MB")
