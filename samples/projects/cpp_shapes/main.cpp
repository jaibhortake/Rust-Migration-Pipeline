#include <algorithm>
#include <iomanip>
#include <iostream>
#include <memory>
#include <vector>
#include "circle.h"
#include "rect.h"

int main() {
    std::vector<std::unique_ptr<Shape>> shapes;
    std::string kind;
    while (std::cin >> kind) {
        if (kind == "c") {
            double r;
            if (!(std::cin >> r) || r < 0) { std::cout << "bad circle\n"; continue; }
            shapes.push_back(std::make_unique<Circle>(r));
        } else if (kind == "r") {
            double w, h;
            if (!(std::cin >> w >> h) || w < 0 || h < 0) { std::cout << "bad rect\n"; continue; }
            shapes.push_back(std::make_unique<Rect>(w, h));
        } else {
            std::cout << "unknown " << kind << "\n";
        }
    }
    std::stable_sort(shapes.begin(), shapes.end(),
                     [](const std::unique_ptr<Shape>& a, const std::unique_ptr<Shape>& b) { return a->area() < b->area(); });
    double total = 0;
    std::cout << std::fixed << std::setprecision(2);
    for (const auto& s : shapes) {
        std::cout << s->name() << " " << s->area() << " " << s->perimeter() << "\n";
        total += s->area();
    }
    std::cout << "total " << total << " count " << shapes.size() << "\n";
    return 0;
}
