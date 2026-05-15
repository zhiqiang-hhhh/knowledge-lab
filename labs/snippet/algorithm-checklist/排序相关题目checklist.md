# 排序相关算法题清单

## 1. 入门（比较排序 + 基础应用）
- [LC 912 排序数组](https://leetcode.com/problems/sort-an-array/)（快排/归并/堆排）
- [LC 88 合并两个有序数组](https://leetcode.com/problems/merge-sorted-array/)（双指针）
- [LC 21 合并两个有序链表](https://leetcode.com/problems/merge-two-sorted-lists/)（归并思想）
- [LC 147 对链表进行插入排序](https://leetcode.com/problems/insertion-sort-list/)（插入排序）
- [LC 75 颜色分类](https://leetcode.com/problems/sort-colors/)（三路划分）

## 2. TopK 与选择问题
- [LC 215 数组中的第K个最大元素](https://leetcode.com/problems/kth-largest-element-in-an-array/)（快速选择/堆）
- [LC 347 前 K 个高频元素](https://leetcode.com/problems/top-k-frequent-elements/)（哈希 + 堆/桶）
- [LC 973 最接近原点的 K 个点](https://leetcode.com/problems/k-closest-points-to-origin/)（堆/快速选择）
- [LC 692 前K个高频单词](https://leetcode.com/problems/top-k-frequent-words/)（堆 + 自定义排序）

## 3. 自定义排序与比较器
- [LC 179 最大数](https://leetcode.com/problems/largest-number/)（自定义比较器）
- [LC 56 合并区间](https://leetcode.com/problems/merge-intervals/)（按左端点排序）
- [LC 57 插入区间](https://leetcode.com/problems/insert-interval/)（排序 + 合并）
- [LC 406 根据身高重建队列](https://leetcode.com/problems/queue-reconstruction-by-height/)（多关键字排序）
- [LC 524 通过删除字母匹配到字典里最长单词](https://leetcode.com/problems/longest-word-in-dictionary-through-deleting/)（长度+字典序排序）

## 4. 计数排序 / 桶排序 / 基数排序思维
- [LC 164 最大间距](https://leetcode.com/problems/maximum-gap/)（桶排序）
- [LC 220 存在重复元素 III](https://leetcode.com/problems/contains-duplicate-iii/)（桶划分）
- [LC 451 根据字符出现频率排序](https://leetcode.com/problems/sort-characters-by-frequency/)（桶思想）
- [LC 1122 数组的相对排序](https://leetcode.com/problems/relative-sort-array/)（计数排序）
- [LC 274 H 指数](https://leetcode.com/problems/h-index/)（计数统计）

## 5. 逆序对与归并统计
- [LC 315 计算右侧小于当前元素的个数](https://leetcode.com/problems/count-of-smaller-numbers-after-self/)（归并排序统计）
- [LC 493 翻转对](https://leetcode.com/problems/reverse-pairs/)（归并排序统计）
- [剑指 Offer 51 数组中的逆序对](https://leetcode.com/problems/shu-zu-zhong-de-ni-xu-dui-lcof/)（归并排序）

## 6. 区间与事件排序（高频建模）
- [LC 252 会议室](https://leetcode.com/problems/meeting-rooms/)（区间排序）
- [LC 253 会议室 II](https://leetcode.com/problems/meeting-rooms-ii/)（排序 + 堆）
- [LC 435 无重叠区间](https://leetcode.com/problems/non-overlapping-intervals/)（排序 + 贪心）
- [LC 452 用最少数量的箭引爆气球](https://leetcode.com/problems/minimum-number-of-arrows-to-burst-balloons/)（排序 + 贪心）

## 7. 字符串/日志类排序
- [LC 49 字母异位词分组](https://leetcode.com/problems/group-anagrams/)（排序作为 key）
- [LC 937 重新排列日志文件](https://leetcode.com/problems/reorder-data-in-log-files/)（稳定排序 + 规则比较）
- [LC 1451 重新排列句子中的单词](https://leetcode.com/problems/rearrange-words-in-a-sentence/)（稳定排序）

## 8. 进阶综合（排序 + 其他结构）
- [LC 23 合并 K 个升序链表](https://leetcode.com/problems/merge-k-sorted-lists/)（堆/分治归并）
- [LC 378 有序矩阵中第 K 小的元素](https://leetcode.com/problems/kth-smallest-element-in-a-sorted-matrix/)（堆/二分）
- [LC 4 寻找两个正序数组的中位数](https://leetcode.com/problems/median-of-two-sorted-arrays/)（分治/二分）
- [LC 295 数据流的中位数](https://leetcode.com/problems/find-median-from-data-stream/)（对顶堆，动态有序）

## 建议刷题顺序
1. 先刷 912/75/88/215/56（建立排序与分区主干）
2. 再刷 347/973/179/164/315（TopK、自定义排序、线性排序、归并统计）
3. 最后做 253/378/4/295 这类综合题（排序与堆/二分结合）
