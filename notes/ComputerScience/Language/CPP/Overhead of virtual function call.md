一次虚函数本身的调用开销并不高。虚函数调用对程序执行速度的影响在于影响cpu进行代码执行的分支预测效率。
导致cpu的pipeline中充满了泡沫。

https://web.archive.org/web/20210225014950/http://assemblyrequired.crashworks.org/how-slow-are-virtual-functions-really/

