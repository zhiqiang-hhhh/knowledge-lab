
<!-- @import "[TOC]" {cmd="toc" depthFrom=1 depthTo=6 orderedList=false} -->

<!-- code_chunk_output -->

- [Logical plan](#logical-plan)
- [Rewrite](#rewrite)
  - [RewriteJob](#rewritejob)
- [Physical plan to PlanFragment](#physical-plan-to-planfragment)

<!-- /code_chunk_output -->

```plantuml
Plan -up-> TreeNode
LogicalPlan -up-> Plan
AbstractLogicalPlan -up-> LogicalPlan
PhysicalPlanTranslator -up-> DefaultPlanVisitor

interface Plan {
    + {abstract} accept(PlanVisitor<R, C> visitor, C context) : <R, C> R
}

interface PlanVisitor {
    + {abstract} visit(Plan plan, C context) : R
    + visitCommand(Command, context) : R
    + visitLogicalXXX(LogicalXXX, context) : R
}

DefaultPlanVisitor -up-> PlanVisitor

class DefaultPlanVisitor<R,C> {
    + visit(Plan, C Context) : R
}
note right of DefaultPlanVisitor::"visit(Plan, C Context)"
for (Plan child : plan.children())
{
    child.accept(this, context);
}
end note

class PhysicalPlanTranslator<PlanFragment,PlanTranslatorContext> {
    - context : PlanTranslatorContext
    + translate(PhysicalPlan) : PlanFragment
    + visitPhysicalXXX(PhysicalXXX, context) : PlanFragment
}

PhysicalXXX -up-> Plan

class PhysicalXXX {
    + accept(PlanVisitor<R, C> visitor, C context) : <R, C> R
}
note left of PhysicalXXX::"accept(PlanVisitor<R, C> visitor, C context) : <R, C> R"
    call visitor.visitPhysicalXXX
end note
```

```java
class PhysicalDistribute {
    public <R, C> R accept(PlanVisitor<R, C> visitor, C context) {
        return visitor.visitPhysicalDistribute(this, context);
    }
}
```


### Logical plan


### Rewrite
```plantuml
FoldConstantRuleOnFE -up-> AbstractExpressionRewriteRule
AbstractExpressionRewriteRule -up-> DefaultExpressionRewriter
AbstractExpressionRewriteRule -up-> ExpressionRewriteRule
DefaultExpressionRewriter -up-> ExpressionVisitor
interface ExpressionVisitor

interface DefaultExpressionRewriter {
    + {static} rewrite(ExpressionVisitor, Expression) : Expression
}
note right of DefaultExpressionRewriter::"rewrite(ExpressionVisitor, Expression)"
new_child = null
for each child_expr : expr:
    new_child = child_expr.accept
return expr.withChildren(new_child)
end note
interface ExpressionRewriteRule {
    + {abstract} rewrite(Expression, T) : Expression
}

Rewriter -up-> AbstractBatchJobExecutor

interface AbstractBatchJobExecutor {
    + static jobs(RewriteJob...) : List<RewriteJob>
    + {abstract} getJobs() : List<RewriteJob>
    + execute() : void
}

class Rewriter {
    + static Rewriter getWholeTreeRewriter(Context)
}
```

```java
class NereidsPlanner {
    private void rewrite() {
        Rewriter.getWholeTreeRewriter(cascadesContext).execute();
    }
}
```
`getWholeTreeRewriter` 是一个工厂方法，用来构造指定类型的 Rewriter 对象，Rewriter 对象构造时需要传入一组 RewriteJob，这组 RewriterJob 是通过另一个工厂方法 `getWholeTreeRewriteJobs` 得到的
```java
public static Rewriter getWholeTreeRewriter(CascadesContext cascadesContext) {
    return new Rewriter(cascadesContext, WHOLE_TREE_REWRITE_JOBS);
}

private static final List<RewriteJob> WHOLE_TREE_REWRITE_JOBS
            = getWholeTreeRewriteJobs(true);
```
getWholeTreeRewriteJobs 在预先定义好的 static 变量 `CTE_CHILDREN_REWRITE_JOBS` 中增加一些新的 RewriteJob 后返回新的 jobs，这一组 `List<RewriteJob>` 将会在 execute 方法中一个个执行。
```java
private static List<RewriteJob> getWholeTreeRewriteJobs(boolean withCostBased) {
        List<RewriteJob> withoutCostBased = Rewriter.CTE_CHILDREN_REWRITE_JOBS.stream()
                .filter(j -> !(j instanceof CostBasedRewriteJob))
                .collect(Collectors.toList());
        return getWholeTreeRewriteJobs(withCostBased ? CTE_CHILDREN_REWRITE_JOBS : withoutCostBased);
}

private static List<RewriteJob> getWholeTreeRewriteJobs(List<RewriteJob> jobs) {
        return jobs(
                topic("cte inline and pull up all cte anchor",
                        custom(RuleType.PULL_UP_CTE_ANCHOR, PullUpCteAnchor::new),
                        custom(RuleType.CTE_INLINE, CTEInline::new)
                ),
                topic("process limit session variables",
                        custom(RuleType.ADD_DEFAULT_LIMIT, AddDefaultLimit::new)
                ),
                topic("rewrite cte sub-tree",
                        custom(RuleType.REWRITE_CTE_CHILDREN, () -> new RewriteCteChildren(jobs))
                ),
                topic("or expansion",
                        topDown(new OrExpansion())),
                topic("whole plan check",
                        custom(RuleType.ADJUST_NULLABLE, AdjustNullable::new)
                )
        );
}
```
#### RewriteJob

```plantuml
CustomRewriteJob -up-> RewriteJob
interface RewriteJob {
    + {abstract} execute(Context) : void
}

interface CustomRewriter {
    + {abstract} rewrite(Plan, JonContext) : Plan
}

CustomRewriteJob  *-- CustomRewriter
```
CustomRewriteJob 
```java {.line-numbers}
class AbstractBatchJobExecutor {
    public static RewriteJob custom(RuleType ruleType, Supplier<CustomRewriter> planRewriter) {
        return new CustomRewriteJob(planRewriter, ruleType);
    }
}

public CustomRewriteJob(Supplier<CustomRewriter> rewriter, RuleType ruleType) {
        this.ruleType = Objects.requireNonNull(ruleType, "ruleType cannot be null");
        this.customRewriter = Objects.requireNonNull(rewriter, "customRewriter cannot be null");
}

class CustomRewriteJob {
    public void execute(JobContext context) {
        Set<Integer> disableRules = Job.getDisableRules(context);
        if (disableRules.contains(ruleType.type())) {
            return;
        }

        Plan root = context.getCascadesContext().getRewritePlan();
        Plan rewrittenRoot = customRewriter.get().rewriteRoot(root, context);
        if (rewrittenRoot == null) {
            return;
        }

        context.getCascadesContext().setRewritePlan(rewrittenRoot);
    }
}
```
第 19 行的 customRewriter 是最初构造时传入的参数，对于不同的规则，构造不同的 CustomRewriter，比如对于`RuleType.REWRITE_CTE_CHILDREN` 就有 `RewriteCteChildren`
```java
public class RewriteCteChildren {
    public Plan rewriteRoot(Plan plan, JobContext jobContext) {
        return plan.accept(this, jobContext.getCascadesContext());
    }
}
```
Plan 是一个树状的数据结构，在这里需要改写的是 LogicalPlan，Doris 使用如下的代码模式去实现对 LogicalPlan 上每个 PlanNode 的改写
```java
public interface Plan extends TreeNode<Plan> {
    ...
    <R, C> R accept(PlanVisitor<R, C> visitor, C context);
    ...
}

public interface LogicalPlan extends Plan {
    ...
}

punlic LogicalResultSink extends LogicalPlan {
    @Override
    public <R, C> R accept(PlanVisitor<R, C> visitor, C context) {
        return visitor.visitLogicalResultSink(this, context);
    }
}

public LogicalXXX extends LogicalPlan {
    @Override
    public <R, C> R accept(PlanVisitor<R, C> visitor, C context) {
        return visitor.visitLogicalXXX(this, context);
    }
}
```
每个 Plan 有一个 accept 方法，这是一个模板函数。
对于每个 LogicalXXX，其 accept 函数里会调用 visitor 的 visitLogicalXXX 方法，visitXXX 方法会把当前的 LogicalXXX 进行改写

```java
class FoldConstantRuleOnFE {
    @Override
    public Expression visitCast(Cast cast, ExpressionRewriteContext context) {
        ...
        
    }
}
```


### Physical plan to PlanFragment

```java
public class StmtExecutor {
    private void executeByNereids(queryId) throws Exception {
        ...
        planner = new NereidsPlanner(statementContext);
        try {
            planner.plan(parsedStmt, context.getSessionVariable().toThrift());
            checkBlockRules();
        }
        ...
        handleQueryWithRetry(queryId);
    }
}

public class NereidsPlanner extends Planner {
    ...
    Plan resultPlan = plan(parsedPlan, requireProperties, explainLevel);
}

```



```java{.line-numbers}
public class NereidsPlanner extends Planner {
    ...
    @Override
    public void plan(StatementBase queryStmt, org.apache.doris.thrift.TQueryOptions queryOptions) {
        ...
        PlanFragment root = physicalPlanTranslator.translatePlan(physicalPlan);
        ...
    }
}
```
上面第 6 行完成物理执行计划到 PlanFramgnet 的转换。也就是在下面的函数里完成的
```java
public class PhysicalPlanTranslator extends DefaultPlanVisitor<PlanFragment, PlanTranslatorContext> {
    ...
    public PlanFragment translatePlan(PhysicalPlan physicalPlan) {
        PlanFragment rootFragment = physicalPlan.accept(this, context);
        ...
        return rootFragment;
    }
    ...
}
```
这里 PhysicalPlan 是一个树状的数据结构，它继承自 Plan:
```java
public interface Plan extends TreeNode<Plan> {
    ...
    <R, C> R accept(PlanVisitor<R, C> visitor, C context);
    ...
}

public interface PhysicalPlan extends Plan {
    ...
}

public PhysicalXXX extends PhysicalPlan {
    @Override
    public <R, C> R accept(PlanVisitor<R, C> visitor, C context) {
        return visitor.visitXXX(this, context);
    }
}
```
每个 Plan 有一个 accept 方法，这是一个模板函数。
对于每个 PhysicalXXX，其 accept 函数里会调用 visitor 的 visitXXX 方法，visitXXX 方法将会把当前的 PhysicalPlan 转成一个 PlanFragment。

比如 PhysicalOlapScan:
```java
public interface LeafPlan extends Plan, LeafNode<Plan> {
    ...
}

public abstract class PhysicalLeaf extends AbstractPhysicalPlan implements LeafPlan {
    ...
}

public abstract class PhysicalRelation extends PhysicalLeaf implements Relation {
    ...
}

public abstract class PhysicalCatalogRelation extends PhysicalRelation implements CatalogRelation {
    ...
}

public class PhysicalOlapScan implements PhysicalCatalogRelation {
    ...
    @Override
    public <R, C> R accept(PlanVisitor<R, C> visitor, C context) {
        return visitor.visitPhysicalOlapScan(this, context);
    }
    ...
}
```
PhysicalOlapScan 的 accept 方法被实现成调用传入的 PlanVisitor 的 visitPhysicalOlapScan 方法。

PhysicalPlanTranslator 就是一个 Planvisitor 对象，它实现了 visitPhysicalOlapScan 
```java
@Override
    public PlanFragment visitPhysicalOlapScan(PhysicalOlapScan olapScan, PlanTranslatorContext context) {
        ...
        OlapScanNode olapScanNode = new OlapScanNode(olapScan.translatePlanNodeId(), tupleDescriptor, "OlapScanNode");
        
        // TODO: maybe we could have a better way to create fragment
        PlanFragment planFragment = createPlanFragment(olapScanNode, dataPartition, olapScan);
        context.addPlanFragment(planFragment);
        updateLegacyPlanIdToPhysicalPlan(planFragment.getPlanRoot(), olapScan);
        return planFragment;
    }
```
