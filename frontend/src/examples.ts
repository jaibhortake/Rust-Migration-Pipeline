import type { Lang } from './api'
export const EXAMPLES: { name: string; language: Lang; code: string }[] = [
  { name: 'Python: two_sum', language: 'python', code: `def two_sum(nums, target):
    seen = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
    return []

if __name__ == "__main__":
    print(two_sum([2, 7, 11, 15], 9))
` },
  { name: 'C++: fibonacci', language: 'cpp', code: `#include <iostream>
#include <vector>

unsigned long long fib(int n) {
    std::vector<unsigned long long> f(n + 2, 0);
    f[1] = 1;
    for (int i = 2; i <= n; ++i) f[i] = f[i - 1] + f[i - 2];
    return f[n];
}

int main() {
    for (int i = 0; i < 10; ++i) std::cout << fib(i) << " ";
    std::cout << std::endl;
    return 0;
}
` },
]
