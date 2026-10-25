def max_subarray(nums):
    best = cur = nums[0]
    for n in nums[1:]:
        cur = max(n, cur + n)
        best = max(best, cur)
    return best


if __name__ == "__main__":
    values = list(map(int, input().split()))
    print(max_subarray(values))
