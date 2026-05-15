用户名在linux中对应一个 uid & gid，mapping信息保存在 `/etc/passwd` & `/etc/group` 中

uid ： user id，对应用户本身
gid ： groud id，对应用户所属的群组

登陆过程：
1. 判断用户名是否在`/etc/passwd`中
2. 如果存在，则去 home 目录读取 shell 设定
3. 进入 /etc/shadow 中对比密码

/etc/passwd 结构：
```shell
adm:x:3:4:adm:/vat/adm:/sbin/nologin
```
1. 账号名称
2. x：密码占位符，历史原因
3. uid：用户id
4. gid：群组id