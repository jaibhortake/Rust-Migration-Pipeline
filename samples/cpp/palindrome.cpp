#include <cctype>
#include <iostream>
#include <string>
using namespace std;

bool isPalindrome(const string& s) {
    int i = 0, j = (int)s.size() - 1;
    while (i < j) {
        while (i < j && !isalnum((unsigned char)s[i])) i++;
        while (i < j && !isalnum((unsigned char)s[j])) j--;
        if (tolower((unsigned char)s[i]) != tolower((unsigned char)s[j])) return false;
        i++;
        j--;
    }
    return true;
}

int main() {
    string line;
    getline(cin, line);
    cout << (isPalindrome(line) ? "true" : "false") << endl;
    return 0;
}
