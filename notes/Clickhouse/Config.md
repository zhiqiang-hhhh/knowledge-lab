```plantuml
BaseDaemon <-- Server
IServer <-- Server

class IServer
{
    {abstract} config() : Configuration
    {abstract} context() : ContextMutablePtr
}

class Server
```
关于 path
```c++
Server::main()
{
    ...
    std::string path_str = getCanonicalPath(config().getString("path", DBMS_DEFAULT_PATH));
    fs::path path = path_str;
    ...
    global_context->setPath(path_str);
    ...
}
```
Disk

```c++
DiskSelector::DiskSelector(const Poco::Util::AbstractConfiguration & config, const String & config_prefix, ContextPtr context)
{
    Poco::Util::AbstractConfiguration::Keys keys;
    config.keys(config_prefix, keys);

    auto & factory = DiskFactory::instance();

    constexpr auto default_disk_name = "default";
    bool has_default_disk = false;
    for (const auto & disk_name : keys)
    {
        if (!std::all_of(disk_name.begin(), disk_name.end(), isWordCharASCII))
            throw Exception("Disk name can contain only alphanumeric and '_' (" + disk_name + ")", ErrorCodes::EXCESSIVE_ELEMENT_IN_CONFIG);

        if (disk_name == default_disk_name)
            has_default_disk = true;

        auto disk_config_prefix = config_prefix + "." + disk_name;

        disks.emplace(disk_name, factory.create(disk_name, config, disk_config_prefix, context, disks));
    }
    if (!has_default_disk)
    {
        std::shared_ptr<IDisk> default_disk = std::make_shared<DiskLocal>(
            default_disk_name, context->getPath(), 0, context, config.getUInt("local_disk_check_period_ms", 0));
        default_disk->startup();
        disks.emplace(default_disk_name, std::make_shared<DiskRestartProxy>(default_disk));
    }
}
```
如果在 disks 中没有显示指定 default，那么会使用 config.xml 中的 path 作为参数创建一个 DiskLocal 类型作为 default disk。

StoragePolicy

```c++
StoragePolicySelectorPtr Context::getStoragePolicySelector(std::lock_guard<std::mutex> & lock) const
{
    if (!shared->merge_tree_storage_policy_selector)
    {
        constexpr auto config_name = "storage_configuration.policies";
        const auto & config = getConfigRef();

        shared->merge_tree_storage_policy_selector = std::make_shared<StoragePolicySelector>(config, config_name, getDiskSelector(lock));
    }
    return shared->merge_tree_storage_policy_selector;
}

StoragePolicySelector::StoragePolicySelector(
    const Poco::Util::AbstractConfiguration & config,
    const String & config_prefix,
    DiskSelectorPtr disks)
{
    Poco::Util::AbstractConfiguration::Keys keys;
    config.keys(config_prefix, keys);

    for (const auto & name : keys)
    {
        if (!std::all_of(name.begin(), name.end(), isWordCharASCII))
            throw Exception(
                "Storage policy name can contain only alphanumeric and '_' (" + backQuote(name) + ")", ErrorCodes::EXCESSIVE_ELEMENT_IN_CONFIG);

        /*
         * A customization point for StoragePolicy, here one can add his own policy, for example, based on policy's name
         * if (name == "MyCustomPolicy")
         *      policies.emplace(name, std::make_shared<CustomPolicy>(name, config, config_prefix + "." + name, disks));
         *  else
         */

        policies.emplace(name, std::make_shared<StoragePolicy>(name, config, config_prefix + "." + name, disks));
        LOG_INFO(&Poco::Logger::get("StoragePolicySelector"), "Storage policy {} loaded", backQuote(name));
    }

    /// Add default policy if it isn't explicitly specified.
    if (policies.find(DEFAULT_STORAGE_POLICY_NAME) == policies.end())
    {
        auto default_policy = std::make_shared<StoragePolicy>(DEFAULT_STORAGE_POLICY_NAME, config, config_prefix + "." + DEFAULT_STORAGE_POLICY_NAME, disks);
        policies.emplace(DEFAULT_STORAGE_POLICY_NAME, std::move(default_policy));
    }
}
```
如果没有名称为 default 的 storage_policy，则会默认创建一个。

```c++
StoragePolicy::StoragePolicy(StoragePolicyPtr storage_policy,
        const Poco::Util::AbstractConfiguration & config,
        const String & config_prefix,
        DiskSelectorPtr disks)
    : StoragePolicy(storage_policy->getName(), config, config_prefix, disks)
{
    for (auto & volume : volumes)
    {
        if (storage_policy->containsVolume(volume->getName()))
        {
            auto old_volume = storage_policy->getVolumeByName(volume->getName());
            try
            {
                auto new_volume = updateVolumeFromConfig(old_volume, config, config_prefix + ".volumes." + volume->getName(), disks);
                volume = std::move(new_volume);
            }
            catch (Exception & e)
            {
                /// Default policies are allowed to be missed in configuration.
                if (e.code() != ErrorCodes::NO_ELEMENTS_IN_CONFIG || storage_policy->getName() != DEFAULT_STORAGE_POLICY_NAME)
                    throw;

                Poco::Util::AbstractConfiguration::Keys keys;
                config.keys(config_prefix, keys);
                if (!keys.empty())
                    throw;
            }
        }
    }
}

StoragePolicy::StoragePolicy(
    String name_,
    const Poco::Util::AbstractConfiguration & config,
    const String & config_prefix,
    DiskSelectorPtr disks)
    : name(std::move(name_))
{
    Poco::Util::AbstractConfiguration::Keys keys;
    String volumes_prefix = config_prefix + ".volumes";

    if (!config.has(volumes_prefix))
    {
        if (name != DEFAULT_STORAGE_POLICY_NAME)
            throw Exception("Storage policy " + backQuote(name) + " must contain at least one volume (.volumes)", ErrorCodes::NO_ELEMENTS_IN_CONFIG);
    }
    else
    {
        config.keys(volumes_prefix, keys);
    }

    for (const auto & attr_name : keys)
    {
        if (!std::all_of(attr_name.begin(), attr_name.end(), isWordCharASCII))
            throw Exception(
                "Volume name can contain only alphanumeric and '_' in storage policy " + backQuote(name) + " (" + attr_name + ")", ErrorCodes::EXCESSIVE_ELEMENT_IN_CONFIG);
        volumes.emplace_back(createVolumeFromConfig(attr_name, config, volumes_prefix + "." + attr_name, disks));
    }

    if (volumes.empty() && name == DEFAULT_STORAGE_POLICY_NAME)
    {
        auto default_volume = std::make_shared<VolumeJBOD>(DEFAULT_VOLUME_NAME, std::vector<DiskPtr>{disks->get(DEFAULT_DISK_NAME)}, 0, false);
        volumes.emplace_back(std::move(default_volume));
    }

    if (volumes.empty())
        throw Exception("Storage policy " + backQuote(name) + " must contain at least one volume.", ErrorCodes::NO_ELEMENTS_IN_CONFIG);

    const double default_move_factor = volumes.size() > 1 ? 0.1 : 0.0;
    move_factor = config.getDouble(config_prefix + ".move_factor", default_move_factor);
    if (move_factor > 1)
        throw Exception("Disk move factor have to be in [0., 1.] interval, but set to " + toString(move_factor) + " in storage policy " + backQuote(name), ErrorCodes::LOGICAL_ERROR);

    buildVolumeIndices();
}
```
对于隐式构建的 default policy，会使用 default disk 构建一个 JBOD 类型的 volume
