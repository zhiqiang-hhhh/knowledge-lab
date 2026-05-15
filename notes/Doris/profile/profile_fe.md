```java
public class RuntimeProfile {
    Map<String, Counter> counterMap;
    Map<String, TreeSet<String>> childCounterMap;
    Map<String, RuntimeProfile> childMap = Maps.newConcurrentMap();
}
```


```java
private RuntimeProfile getPipelineAggregatedProfile(Map<Integer, String> planNodeMap) {
        RuntimeProfile fragmentsProfile = new RuntimeProfile("Fragments");
        for (int i = 0; i < fragmentProfiles.size(); ++i) {
            RuntimeProfile newFragmentProfile = new RuntimeProfile("Fragment " + i);
            fragmentsProfile.addChild(newFragmentProfile);
            List<List<RuntimeProfile>> allPipelines = getMultiBeProfile(seqNoToFragmentId.get(i));
            int pipelineIdx = 0;
            for (List<RuntimeProfile> allPipelineTask : allPipelines) {
                RuntimeProfile mergedpipelineProfile = null;
                if (allPipelineTask.isEmpty()) {
                    // It is possible that the profile collection may be incomplete, so only part of
                    // the profile will be merged here.
                    mergedpipelineProfile = new RuntimeProfile(
                            "Pipeline : " + pipelineIdx + "(miss profile)",
                            -pipelineIdx);
                } else {
                    mergedpipelineProfile = new RuntimeProfile(
                            "Pipeline : " + pipelineIdx + "(instance_num="
                                    + allPipelineTask.size() + ")",
                            allPipelineTask.get(0).nodeId());
                    RuntimeProfile.mergeProfiles(allPipelineTask, mergedpipelineProfile, planNodeMap);
                }
                newFragmentProfile.addChild(mergedpipelineProfile);
                pipelineIdx++;
                fragmentsProfile.rowsProducedMap.putAll(mergedpipelineProfile.rowsProducedMap);
            }
        }
        return fragmentsProfile;
    }
```
