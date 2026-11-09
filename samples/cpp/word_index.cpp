#include <algorithm>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

int main() {
    std::map<std::string, std::set<int>> index;
    std::string line;
    int lineNo = 0;
    while (std::getline(std::cin, line)) {
        lineNo++;
        std::istringstream in(line);
        std::string word;
        while (in >> word) {
            std::string clean;
            for (char c : word)
                if (std::isalnum(static_cast<unsigned char>(c))) clean += c;
            if (!clean.empty()) index[lower(clean)].insert(lineNo);
        }
    }
    std::vector<std::pair<std::string, std::set<int>>> entries(index.begin(), index.end());
    std::stable_sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) {
        if (a.second.size() != b.second.size()) return a.second.size() > b.second.size();
        return a.first < b.first;
    });
    for (const auto& [word, lines] : entries) {
        std::cout << word << ":";
        for (int n : lines) std::cout << " " << n;
        std::cout << "\n";
    }
    std::cout << "distinct " << index.size() << " lines " << lineNo << "\n";
    return 0;
}
