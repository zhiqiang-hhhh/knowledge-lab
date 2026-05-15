[TOC]

# Transactions

## Transaction Concept
A transaction is a unit of program execution that accesses and possibly updates various data items. 

事务的四个重要特性：
* Atomicity 事务的所有操作不然全部都反应在数据库中，不然全部都不。
* Consistency 单独执行事务可以保持数据库的一致性。Logically correct
* Isolation 即使多个事务并发执行，系统也需要保证，对于每一对事务 Ti 和 Tj，无论 Tj 在 Ti 开始之前就结束，还是 Tj 在 Ti 结束之后才开始，对于 Ti 来说，它不会被系统中其他并发执行的事务影响。
* Durability 当某个事务成功完成后，即使遇到 system failures，它所做出的变化也需要持久化到数据库中

以上统称为 ACID

## A Simple Transaction Model
* read(X), transfers data item X from database to a variable, also called X, in a buffer in memory belonging to the transaction that executed the read operation
* write(X), treansfers the value of variable X in the main-memory buffer of the transaction that executed the write to the data item X in the database.

**当前，我们先假设 write(X) 能够成功将 X 写入磁盘**

事务 Ti：从账户 A 转账$50 到账户 B

    Ti: read(A);
        A := A - 50
        write(A);
        read(B);
        B := B + 50
        write(B)

ACID:
* Consistency: Sum of A and B unchanged after transaction.
* Atomicity: 转账到一半，system failures happen，需要保证重启之后 A 的钱没少，B 的钱没多。**需要注意，这一过程中，系统在某些时刻处于 inconsistent state, 是可能的，需要保证该状态对外部不可见**。atomicity 主要是由 recovery system 保障
* Durability: 一旦调用者得到提示，转账完成，那么后续的 system failure 不应当对已有的成功造成影响
* Isolation：Concurrently executed transcations may result in an inconsistent state. 比如，在 Ti 执行期间的某个 inconsistent moment，Tj 开始执行 sum(A, B)，那么就可能得到错误答案。
  避免并发问题的一个方法是将事务顺序执行（serially）。The isolation property of a transaction ensures that the concurrent execution of transactions results in a system state that is equivalent to a state that could have been obtained had these transactions executed one at a time in some order

## Transaction Atomicity and Durability
Transaction may not complete its execution successfully, such a transaction is termed **aborted**.
我们需要将这类 txn 所做的 change 撤销，该过程叫做 **roll back**
This is done typically by maintaining a **log**. 
Transaction that completes its execution successfully is said to be **committed**.

Transaction states:
* Active, the initial state; the transaction stays in this state while it is executing.
* Partially committed, after the final statement has been executed.
* Failed, after the discovery that normal execution can no longer proceed
* Aborted, after the transaction has been rolled back and the database has been restored to its state prior to the start of the transaction.
* Committed, after successful completion

## Transaction Isolation
定义两个事务并发执行

        T1                  T2
        read(A);        
        A := A − 50;        
        write(A);
                            read(A);
                            temp := A*0.1;
                            A := A - temp;
                            write(A);
        read(B); 
        B := B + 50;        
        write(B).           
        committed                            
                            read(B);
                            B := B + temp;
                            write(B).
                            committed

上图所示的并发执行顺序下，最终是可以保证数据库的一致性的。但是，并不是所有的执行都可以导致正确的状态。因此，**事务的并发执行顺序不能交给操作系统去决定**。The concurrency-control component of the database system carries out this task.

**The schedule should be equivalent to a serial schedule, such schedules are called serializable schedules.**



## Serializability
这一节我们讨论如何判断某个 schedule 是 serializable。很明显，serial schedules are serializable。但是如果多个事务的各个步骤之间交错（interleaved），那么我们很难判断该 schedule 是否为 serializable。

关注**conflict serializability**

I -> Ti, J -> Tj，I 和 J 是 Read/Write 中的一个，那么我们有四种组合：
* I = Read(Q), J = Read(Q) 那么 Order does not matter.
* I = Read(Q), J = Write(Q), 如果 I 在 J 前，I 读的是旧值；如果 I 在 J 后，那么 I 读的是 J 写入的值，因此 I 与 J 的顺序对结果有关系
* I = Write(Q), J = Read(Q), 同上，Order matters
* I = Write(Q), J = Write(Q), Order matters

只有当两个操作都为读操作时，操作的相对顺序才不会有影响。
We say that I and J **conflict** if they are operations by different transactions on the same data item, and at least one of these instructions is a write operation.

* READ-WRITE CONFLICTS

        T1                  T2
        read(A);        
                            read(A);
                            temp := A*0.1;
                            A := A - temp;
                            write(A);
        read(A); 
        committed   

很明显，T1 的两次 READ 会读取到前后不同的结果。    
* WRITE-READ CONFLICTS                         

        T1                  T2
        read(A); 
        A := A + 2       
        write(A); 
                            read(A);
                            A := A + 2
                            write(A);
                            committed
        abort
T1 将对 A 的改动写入了 database，该结果被 T2 读取，并且使用。然而 T1 最终决定 abort，这意味着我们需要 roll back T1，但是问题在于 T2 已经读取了 T1 需要被撤销的操作结果。

* WRITE-WRITE CONFLICTS
  
        T1                  T2
        W(A)
                            W(A)
                            W(B)
                            committed
        W(B)
        committed
        
overwrite uncommitted txn

If a schedule S can be transformed into a schedule S′ by a series of swaps of nonconflicting instructions, we say that S and S′ are conflict equivalent.

We say that a schedule S is conflict serializable if it is conflict equivalent to a serial schedule by swap instruction order.

如何判断某个 schedule is conflect serializable？DEPENDENCY GRAPHS
Consider a schedule S. We construct a directed graph, called a **precedence graph**, from S.
