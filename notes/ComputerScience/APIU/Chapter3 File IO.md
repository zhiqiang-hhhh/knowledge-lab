File descriptor: refer to ALL types of open files, including pipes, FIFOS, sockets, terminals, devices, and regular files.

UNIX IO 具有一致性：所有的IO操作都可以通过四个系统调用完成，不论参与IO的设备具体是什么。
Universality of I/O is achieved by ensuring that each file system and device driver implements the same set of I/O system calls. 
当我们需要利到某个文件系统或者磁盘驱动的特有能力时，使用 ioctl() 系统调用。