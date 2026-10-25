#include <string>
#include <vector>
using namespace std;

string longestCommonPrefix(const vector<string>& strs) {
    if (strs.empty()) return "";
    string prefix = strs[0];
    for (size_t i = 1; i < strs.size(); i++) {
        size_t k = 0;
        while (k < prefix.size() && k < strs[i].size() && prefix[k] == strs[i][k]) k++;
        prefix = prefix.substr(0, k);
    }
    return prefix;
}
