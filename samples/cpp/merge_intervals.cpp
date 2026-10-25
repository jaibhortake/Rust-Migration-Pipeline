#include <algorithm>
#include <vector>
using namespace std;

vector<vector<int>> mergeIntervals(vector<vector<int>> intervals) {
    sort(intervals.begin(), intervals.end());
    vector<vector<int>> result;
    for (const auto& iv : intervals) {
        if (!result.empty() && iv[0] <= result.back()[1]) {
            result.back()[1] = max(result.back()[1], iv[1]);
        } else {
            result.push_back(iv);
        }
    }
    return result;
}
