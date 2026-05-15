# System-Level IO

File type:
- **Regular file**: contains arbitrary data.
- **Directory**: a file consisting of an array of links, where each link maps a filename to a file. 每个目录最少包含两条entry：
    - .(dot) 指向自己
    - ..(dot-dot) 指向父目录
- **socket**: communicate with other processes

注意，以上的文件类型是对于操作系统来说的。其他的一些类型，如文本文件、二进制文件等是对于应用来说的，对OS来说，这些都是regular file。

其他还有一些文件类型：_named pipes, symbolic links, charactor and block device_

每个进程都有一个自己的进程上下文，其中有一项：a current working directory

