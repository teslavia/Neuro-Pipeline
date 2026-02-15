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
 * Also supports list items (lines starting with "- ") under a section,
 * producing indexed keys like "cameras.0.device", "cameras.1.device".
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
    int list_index = -1;
    std::string list_section;

    while (std::getline(file, line)) {
      auto comment_pos = line.find('#');
      if (comment_pos != std::string::npos) line.erase(comment_pos);

      // Detect indentation level before trimming
      auto raw_start = line.find_first_not_of(" \t\r\n");
      if (raw_start == std::string::npos) continue;
      int indent = static_cast<int>(raw_start);

      line = line.substr(raw_start);
      auto end = line.find_last_not_of(" \t\r\n");
      if (end != std::string::npos) line.erase(end + 1);
      if (line.empty()) continue;

      // Check for list item: "- key: value"
      if (line.size() >= 2 && line[0] == '-' && line[1] == ' ') {
        if (list_section.empty()) {
          list_section = current_section;
          list_index = 0;
        } else {
          list_index++;
        }
        // Parse "- key: value" or "- value"
        std::string item = line.substr(2);
        auto item_colon = item.find(':');
        if (item_colon != std::string::npos) {
          std::string k = item.substr(0, item_colon);
          std::string v = (item_colon + 1 < item.size()) ? item.substr(item_colon + 1) : "";
          auto trim = [](std::string& s) {
            auto a = s.find_first_not_of(" \t\"");
            auto b = s.find_last_not_of(" \t\"");
            s = (a == std::string::npos) ? "" : s.substr(a, b - a + 1);
          };
          trim(k);
          trim(v);
          std::string full_key = list_section + "." + std::to_string(list_index) + "." + k;
          config_[full_key] = v;
        }
        continue;
      }

      // Not a list item — reset list tracking if indent is at section level
      if (indent == 0 || (indent <= 2 && !line.empty() && line[0] != '-')) {
        list_section.clear();
        list_index = -1;
      }

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
