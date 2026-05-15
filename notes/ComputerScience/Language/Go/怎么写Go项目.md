Go package: 一组 source file，包含在同一个文件夹内。
Go module: 一组 Go packages，这组 packages 将会被一起 release。

一个 Go 仓库包含一个 Go module，位于项目的根目录。go.mod 用于声明 module path：the import path prefix for all packages within the module. Each module's path not only serves as an import path prefix for its packages, but also indicates where the go command should look to download it. 

An import path is a string used to import a package. A package's import path is its module path joined with its subdirectory within the module. 