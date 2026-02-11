#include <iostream>
#include <string>
#include <map>

namespace app {

/**
 * @brief Simple configuration manager for edge application.
 */
class ConfigManager {
 public:
  ConfigManager() = default;

  bool LoadFromFile(const std::string& /*path*/) {
    // TODO: Parse YAML/JSON config file
    // Keys: device_path, model_path, server_address, fps, etc.
    std::cout << "[ConfigManager] LoadFromFile (stub)" << std::endl;
    return false;
  }

  std::string Get(const std::string& key,
                  const std::string& default_value = "") const {
    auto it = config_.find(key);
    return (it != config_.end()) ? it->second : default_value;
  }

  void Set(const std::string& key, const std::string& value) {
    config_[key] = value;
  }

 private:
  std::map<std::string, std::string> config_;
};

}  // namespace app
