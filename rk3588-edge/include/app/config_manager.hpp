#ifndef APP_CONFIG_MANAGER_HPP_
#define APP_CONFIG_MANAGER_HPP_

#include <fstream>
#include <iostream>
#include <map>
#include <string>

namespace app {

/**
 * @brief Simple YAML-subset config parser (section: + key: value).
 *
 * No yaml-cpp dependency. Supports flat sections with string values.
 */
class ConfigManager {
 public:
  ConfigManager() = default;

  bool LoadFromFile(const std::string& path) {
    std::ifstream file(path);
    if (!file.is_open()) {
      std::cerr << "[ConfigManager] Cannot open: " << path << std::endl;
      return false;
    }

    std::string line;
    std::string current_section;
    while (std::getline(file, line)) {
      auto comment_pos = line.find('#');
      if (comment_pos != std::string::npos) line.erase(comment_pos);

      auto start = line.find_first_not_of(" \t\r\n");
      if (start == std::string::npos) continue;
      line = line.substr(start);
      auto end = line.find_last_not_of(" \t\r\n");
      if (end != std::string::npos) line.erase(end + 1);
      if (line.empty()) continue;

      auto colon = line.find(':');
      if (colon == std::string::npos) continue;

      std::string key = line.substr(0, colon);
      std::string value = (colon + 1 < line.size()) ? line.substr(colon + 1) : "";

      auto trim = [](std::string& s) {
        auto a = s.find_first_not_of(" \t\"");
        auto b = s.find_last_not_of(" \t\"");
        s = (a == std::string::npos) ? "" : s.substr(a, b - a + 1);
      };
      trim(key);
      trim(value);

      if (value.empty()) {
        current_section = key;
      } else {
        std::string full_key = current_section.empty()
                                   ? key
                                   : current_section + "." + key;
        config_[full_key] = value;
      }
    }

    std::cout << "[ConfigManager] Loaded " << config_.size()
              << " entries from " << path << std::endl;
    return true;
  }

  std::string Get(const std::string& key,
                  const std::string& default_value = "") const {
    auto it = config_.find(key);
    return (it != config_.end()) ? it->second : default_value;
  }

  int GetInt(const std::string& key, int default_value = 0) const {
    auto it = config_.find(key);
    if (it == config_.end()) return default_value;
    try { return std::stoi(it->second); } catch (...) { return default_value; }
  }

  float GetFloat(const std::string& key, float default_value = 0.0f) const {
    auto it = config_.find(key);
    if (it == config_.end()) return default_value;
    try { return std::stof(it->second); } catch (...) { return default_value; }
  }

  bool GetBool(const std::string& key, bool default_value = false) const {
    auto it = config_.find(key);
    if (it == config_.end()) return default_value;
    return it->second == "true" || it->second == "1" || it->second == "yes";
  }

  void Set(const std::string& key, const std::string& value) {
    config_[key] = value;
  }

  bool Has(const std::string& key) const {
    return config_.find(key) != config_.end();
  }

 private:
  std::map<std::string, std::string> config_;
};

}  // namespace app

#endif  // APP_CONFIG_MANAGER_HPP_
