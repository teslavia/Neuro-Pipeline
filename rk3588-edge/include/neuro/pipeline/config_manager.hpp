#ifndef NEURO_PIPELINE_CONFIG_MANAGER_HPP_
#define NEURO_PIPELINE_CONFIG_MANAGER_HPP_

#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace neuro::pipeline {

/**
 * @brief Simple YAML-subset config parser with nested section + list support.
 *
 * No yaml-cpp dependency. Supports nested sections via indentation tracking,
 * producing dotted keys like "edge.recording.enabled". Also supports list
 * items (lines starting with "- ") producing indexed keys like
 * "edge.models.0.model_id".
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
    // Section stack: (indent_level, section_name) pairs for nested sections
    std::vector<std::pair<int, std::string>> section_stack;
    int list_index = -1;
    std::string list_section;
    int list_indent = -1;

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
          list_section = CurrentSection(section_stack);
          list_index = 0;
          list_indent = indent;
        } else if (indent <= list_indent) {
          // Same or outer indent — new list item
          list_index++;
        }
        // Parse "- key: value" or "- value"
        std::string item = line.substr(2);
        auto item_start = item.find_first_not_of(" \t");
        if (item_start != std::string::npos) item = item.substr(item_start);
        auto item_colon = item.find(':');
        if (item_colon != std::string::npos) {
          std::string k = item.substr(0, item_colon);
          std::string v = (item_colon + 1 < item.size()) ? item.substr(item_colon + 1) : "";
          TrimValue(k);
          TrimValue(v);
          std::string full_key = list_section + "." + std::to_string(list_index) + "." + k;
          config_[full_key] = v;
        }
        continue;
      }

      // List item continuation: indented deeper than "- " line, belongs to
      // the current list item (e.g. model_path after "- model_id:")
      if (!list_section.empty() && indent > list_indent && list_index >= 0) {
        auto item_colon = line.find(':');
        if (item_colon != std::string::npos) {
          std::string k = line.substr(0, item_colon);
          std::string v = (item_colon + 1 < line.size()) ? line.substr(item_colon + 1) : "";
          TrimValue(k);
          TrimValue(v);
          std::string full_key = list_section + "." + std::to_string(list_index) + "." + k;
          config_[full_key] = v;
        }
        continue;
      }

      // Not a list item — reset list tracking if indent is at or before list level
      if (!list_section.empty() && indent <= list_indent) {
        list_section.clear();
        list_index = -1;
        list_indent = -1;
      }

      // Pop section stack to match current indent level
      while (!section_stack.empty() && section_stack.back().first >= indent) {
        section_stack.pop_back();
      }

      auto colon = line.find(':');
      if (colon == std::string::npos) continue;

      std::string key = line.substr(0, colon);
      std::string value = (colon + 1 < line.size()) ? line.substr(colon + 1) : "";

      // Check if value is a quoted empty string before trimming
      auto raw_value = value;
      auto rv_start = raw_value.find_first_not_of(" \t");
      bool is_quoted_empty = (rv_start != std::string::npos &&
                              raw_value.size() >= rv_start + 2 &&
                              raw_value[rv_start] == '"' &&
                              raw_value[rv_start + 1] == '"');

      TrimValue(key);
      TrimValue(value);

      if (value.empty() && !is_quoted_empty) {
        // Section header — push onto stack
        section_stack.push_back({indent, key});
      } else {
        std::string section = CurrentSection(section_stack);
        std::string full_key = section.empty() ? key : section + "." + key;
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
  static void TrimValue(std::string& s) {
    auto a = s.find_first_not_of(" \t\"");
    auto b = s.find_last_not_of(" \t\"");
    s = (a == std::string::npos) ? "" : s.substr(a, b - a + 1);
  }

  static std::string CurrentSection(
      const std::vector<std::pair<int, std::string>>& stack) {
    std::string result;
    for (const auto& p : stack) {
      if (!result.empty()) result += ".";
      result += p.second;
    }
    return result;
  }

  std::map<std::string, std::string> config_;
};

}  // namespace neuro::pipeline

#endif  // NEURO_PIPELINE_CONFIG_MANAGER_HPP_
