d## 1. INTRODUCTION

PAX table layout improve the read performance from two major dimensions:
* storage-layout optimization that improves the I/O efficiency
* data caching that reduces the amount of I/Os

**Storage-layout Optimization**

**Column ordering** reorders the physical positions of column chunks within the same row group and puts frequently co-accessed column chunks into nearby position. 对于大宽表来说，这种优化很有效，可以大幅减少 disk seek. 
增大 row group 的大小也可以提高 I/O 性能。不过增大 row group 的大小会降低读取数据的效率。

**Data Caching**
