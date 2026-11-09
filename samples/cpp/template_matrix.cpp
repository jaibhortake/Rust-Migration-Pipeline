#include <iostream>
#include <stdexcept>
#include <vector>

template <typename T>
class Matrix {
    int rows_, cols_;
    std::vector<T> data_;

public:
    Matrix(int r, int c) : rows_(r), cols_(c), data_(r * c, T()) {}

    T& at(int r, int c) { return data_[r * cols_ + c]; }
    const T& at(int r, int c) const { return data_[r * cols_ + c]; }
    int rows() const { return rows_; }
    int cols() const { return cols_; }

    Matrix operator*(const Matrix& o) const {
        if (cols_ != o.rows_) throw std::invalid_argument("dimension mismatch");
        Matrix out(rows_, o.cols_);
        for (int i = 0; i < rows_; i++)
            for (int j = 0; j < o.cols_; j++) {
                T sum = T();
                for (int k = 0; k < cols_; k++) sum += at(i, k) * o.at(k, j);
                out.at(i, j) = sum;
            }
        return out;
    }

    Matrix transpose() const {
        Matrix out(cols_, rows_);
        for (int i = 0; i < rows_; i++)
            for (int j = 0; j < cols_; j++) out.at(j, i) = at(i, j);
        return out;
    }
};

template <typename T>
Matrix<T> read(int r, int c) {
    Matrix<T> m(r, c);
    for (int i = 0; i < r; i++)
        for (int j = 0; j < c; j++) std::cin >> m.at(i, j);
    return m;
}

template <typename T>
void print(const Matrix<T>& m) {
    for (int i = 0; i < m.rows(); i++) {
        for (int j = 0; j < m.cols(); j++) std::cout << m.at(i, j) << (j + 1 < m.cols() ? " " : "");
        std::cout << "\n";
    }
}

int main() {
    int r1, c1, r2, c2;
    if (!(std::cin >> r1 >> c1 >> r2 >> c2) || r1 <= 0 || c1 <= 0 || r2 <= 0 || c2 <= 0) {
        std::cout << "bad dimensions\n";
        return 0;
    }
    auto a = read<long long>(r1, c1);
    auto b = read<long long>(r2, c2);
    try {
        print(a * b);
    } catch (const std::invalid_argument& e) {
        std::cout << "error: " << e.what() << "\n";
    }
    print(a.transpose());
    return 0;
}
