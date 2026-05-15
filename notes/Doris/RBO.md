RBO 的整体代码分为两个大部分，一部分是 RBO 框架，一部分是规则实现。
```java
class PlanTreeRewriteJob {
    protected final RewriteResult rewrite(Plan plan, List<Rule> rules, RewriteJobContext rewriteJobContext) {
        CascadesContext cascadesContext = context.getCascadesContext();
        cascadesContext.setIsRewriteRoot(rewriteJobContext.isRewriteRoot());

        for (Rule rule : rules) {
            if (disableRules.get(rule.getRuleType().type())) {
                continue;
            }
            Pattern<Plan> pattern = (Pattern<Plan>) rule.getPattern();
            if (pattern.matchPlanTree(plan)) {
                List<Plan> newPlans = rule.transform(plan, cascadesContext);
                if (newPlans.size() != 1) {
                    throw new AnalysisException("Rewrite rule should generate one plan: " + rule.getRuleType());
                }
                Plan newPlan = newPlans.get(0);
                if (!newPlan.deepEquals(plan)) {
                    ...
                    rewriteJobContext.result = newPlan;
                    context.setRewritten(true);
                    rule.acceptPlan(newPlan);
                    return new RewriteResult(true, newPlan);
                }
            }
        }
        return new RewriteResult(false, plan);
    }
}
```
遍历输入的所有 Rule，判断当前的 Plan 是否与 Rule 定义的 Pattern 匹配，如果匹配，那么执行 Rule 的 transform 方法，返回改写结果。PlanTreeRewriteJob的 rewrite 方法是 RBO 框架与 RBO 规则实现的分界点，往上查看 rewrite 如何被调用属于 RBO 框架的部分，往下看 Rule 对象如何得到，则属于 RBO 的规则实现部分。

### RBO 规则实现
```plantuml
interface Rule {
    - RuleType ruleType
    - Pattern<? extends Plan> pattern;
    - RulePromise rulePromise
}

class PatternDescriptor<INPUT_TYPE extends Plan> {
    + Pattern<INPUT_TYPE> pattern;
    + RulePromise defaultPromise;
    ...
    + when(Predicate<INPUT_TYPE> predicate) : PatternDescriptor;
    + whenNot(Predicate<INPUT_TYPE> predicate) : PatternDescriptor;
    + then(Function<INPUT_TYPE, OUTPUT_TYPE> matchedAction) : PatternMatcher<INPUT_TYPE, OUTPUT_TYPE>
}

class PatternMatcher<INPUT_TYPE : Plan, OUTPUT_TYPE : Plan> {
    + Pattern<INPUT_TYPE> pattern;
    + RulePromise defaultRulePromise;
    + MatchedAction<INPUT_TYPE, OUTPUT_TYPE> matchedAction;
    + MatchedMultiAction<INPUT_TYPE, OUTPUT_TYPE> matchedMultiAction;
    
    + toRule(RuleType ruleType) : Rule
    + toRule(RuleType ruleType, RulePromise) : Rule
}
```
```java
public class PushDownVectorTopNIntoOlapScan implements RewriteRuleFactory {
    @Override
    public List<Rule> buildRules() {
        return ImmutableList.of(
                    logicalTopN(logicalProject(logicalOlapScan())).when(t -> t.getOrderKeys().size() == 1).then(topN -> {
                        LogicalProject<LogicalOlapScan> project = topN.child();
                        LogicalOlapScan scan = project.child();
                        return pushDown(topN, project, scan, Optional.empty());
                    }).toRule(RuleType.PUSH_DOWN_VIRTUAL_COLUMNS_INTO_OLAP_SCAN),
                    logicalTopN(logicalProject(logicalFilter(logicalOlapScan())))
                            .when(t -> t.getOrderKeys().size() == 1).then(topN -> {
                                LogicalProject<LogicalFilter<LogicalOlapScan>> project = topN.child();
                                LogicalFilter<LogicalOlapScan> filter = project.child();
                                LogicalOlapScan scan = filter.child();
                                return pushDown(topN, project, scan, Optional.of(filter));
                            }).toRule(RuleType.PUSH_DOWN_VIRTUAL_COLUMNS_INTO_OLAP_SCAN)
            );    
}
```
`buildRules` 使用工厂模式构造两个 Rule 对象。
```java
default <C1 extends Plan>
  PatternDescriptor<LogicalTopN<C1>>
          logicalTopN(PatternDescriptor<C1> child1) {
      return new PatternDescriptor<LogicalTopN<C1>>(
          new TypePattern(LogicalTopN.class, child1.pattern),
          defaultPromise()
      );
  }
```
比如 `logicalTopN`是一个工厂方法的名字，构造的是一个`PatternDescriptor`对象。这里代码嵌套了 3 层，构造的是 topn - projection - olapscan 这样的 Pattern 结构。

```java
public PatternDescriptor<INPUT_TYPE> when(Predicate<INPUT_TYPE> predicate) {
        List<Predicate<INPUT_TYPE>> predicates = ImmutableList.<Predicate<INPUT_TYPE>>builder()
                .addAll(pattern.getPredicates())
                .add(predicate)
                .build();
        return new PatternDescriptor<>(pattern.withPredicates(predicates), defaultPromise);
    }
```
PatternDescriptor 的 when 方法则是构造带有 predicate 的 PatternDescriptor 对象。
```java
public <OUTPUT_TYPE extends Plan> PatternMatcher<INPUT_TYPE, OUTPUT_TYPE> then(
            Function<INPUT_TYPE, OUTPUT_TYPE> matchedAction) {
        MatchedAction<INPUT_TYPE, OUTPUT_TYPE> adaptMatchedAction = ctx -> matchedAction.apply(ctx.root);
        return new PatternMatcher<>(pattern, defaultPromise, adaptMatchedAction);
    }
```
PatternDescriptor 的 then 方法则返回一个 `PatternMatcher<INPUT_TYPE, OUTPUT_TYPE>` 对象。
`PatternMatcher` 对象构造的时候需要三个入参，pattern 就是之前的工厂方法返回的 `topn - projection - olapscan`，defaultPromise 则用于描述 Rule 的 apply 顺序，adaptMatchedAction 是一个 Lambda 函数，用来执行改写。
```java
    /**
     * convert current PatternMatcher to a rule.
     *
     * @param ruleType what type of the new rule?
     * @param rulePromise what priority of the new rule?
     * @return Rule
     */
    public Rule toRule(RuleType ruleType, RulePromise rulePromise) {
        return new Rule(ruleType, pattern, rulePromise) {
            @Override
            public List<Plan> transform(Plan originPlan, CascadesContext context) {
                if (matchedMultiAction != null) {
                    MatchingContext<INPUT_TYPE> matchingContext =
                            new MatchingContext<>((INPUT_TYPE) originPlan, pattern, context);
                    List<OUTPUT_TYPE> replacePlans = matchedMultiAction.apply(matchingContext);
                    return replacePlans == null || replacePlans.isEmpty()
                            ? ImmutableList.of(originPlan)
                            : ImmutableList.copyOf(replacePlans);
                } else {
                    MatchingContext<INPUT_TYPE> matchingContext =
                            new MatchingContext<>((INPUT_TYPE) originPlan, pattern, context);
                    OUTPUT_TYPE replacePlan = matchedAction.apply(matchingContext);
                    return ImmutableList.of(replacePlan == null ? originPlan : replacePlan);
                }
            }
        };
    }
```
PatternMatcher 的 toRule 方法则是返回一个对应的 Rule 对象，并且重载了 Rule 对象的 transform 方法。

### RBO 框架
```plantuml
class PlanTreeRewriteJob {
    + rewrite(Plan, List<Rule>, RewriteJobContext) : RewriteResult
}

PlanTreeRewriteTopDownJob -up-> PlanTreeRewriteJob
PlanTreeRewriteBottomUpJob -up-> PlanTreeRewriteJob
PlanTreeRewriteJob -up-> Job
```
TopDwonJob 和 BottomUpJob 表示的是两种递归模式：
TopDownJob 表示当 pattern 满足，并且重写当前节点产生新的节点之后，再次重写当前节点。
BottomUpJob 表示从子节点开始向上递归，重写过程中如果有新的节点产生，那么会从所有子树重新走一遍。
关于这两种策略，先不细看了，比较复杂，具体的执行流程得去 debug 调度过程了。