```plantuml
class LoadLoadingTask extends LoadTask {
    - int profileLevel;
    # {abstract} void executeTask();
}

class CloudLoadLoadingTask extends LoadLoadingTask {
}

abstract class LoadTask extends MasterTask {}

class BrokerLoadJob extends BulkLoadJob {
    - int profileLevel;
}

class BulkLoadJob extends LoadJob {
    - void createLoadingTask()
}

abstract class LoadJob implements LoadTaskCallback, Writable {
    # Map<String, String> sessionVariables;
}

```