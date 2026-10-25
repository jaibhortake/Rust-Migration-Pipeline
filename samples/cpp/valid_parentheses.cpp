#include <iostream>
#include <string>
#include <vector>
using namespace std;

bool isValid(const string& s) {
    vector<char> st;
    for (char ch : s) {
        if (ch == '(' || ch == '[' || ch == '{') {
            st.push_back(ch);
        } else {
            if (st.empty()) return false;
            char o = st.back();
            st.pop_back();
            if ((ch == ')' && o != '(') || (ch == ']' && o != '[') || (ch == '}' && o != '{')) return false;
        }
    }
    return st.empty();
}

int main() {
    string s;
    cin >> s;
    cout << (isValid(s) ? "true" : "false") << endl;
    return 0;
}
