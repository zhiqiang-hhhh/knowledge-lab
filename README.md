# Knowledge Lab

个人技术笔记与实验脚本仓库。

这个仓库由两个本地仓库合并而来：

- `zhiqiang-hhhh.github.io`：技术文章、学习笔记、图片素材、日常记录
- `snippet`：Doris、向量检索、Faiss、DiskANN、HNSW、量化、查询执行等实验脚本和 PoC

## Directory Layout

- `notes/`：长期知识笔记，主要来自原 `pre_post/`
- `posts/`：已经整理成文章形式的内容，主要来自原 `docs/_posts/`
- `daily/`：日常记录
- `assets/images/`：笔记和文章引用的图片资源
- `labs/snippet/`：实验脚本、benchmark、原型代码和报告

## Notes

这个仓库不再按 GitHub Pages/Jekyll 站点组织。原博客发布相关配置没有迁入根目录，内容以个人知识库和实验工作台为主。

`labs/snippet/` 是从原 `snippet` 仓库整体迁入的实验区。为了避免嵌套 Git 仓库影响当前仓库管理，原 `snippet/.git` 已在本地迁移为 `labs/snippet/.git.orig`，并被 `.gitignore` 忽略。
