def transpose(matrix):
    if not matrix:
        return []
    return [[row[j] for row in matrix] for j in range(len(matrix[0]))]


if __name__ == "__main__":
    r, c = map(int, input().split())
    m = [list(map(int, input().split())) for _ in range(r)]
    for row in transpose(m):
        print(" ".join(map(str, row)))
