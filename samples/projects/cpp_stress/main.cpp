#include <iostream>
#include <vector>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <map>
#include <set>
#include <queue>
#include <stack>
#include <memory>
#include <optional>
#include <variant>
#include <tuple>
#include <algorithm>
#include <numeric>
#include <functional>
#include <stdexcept>
#include <sstream>
#include <iomanip>
#include <type_traits>
#include <concepts>
#include <ranges>
#include <cstdint>
#include <limits>

using namespace std;

// ==========================================
// 1. CONCEPTS AND GENERIC PROGRAMMING
// ==========================================

template<typename T>
concept Numeric = is_arithmetic_v<T>;

template<Numeric T>
class Statistics {
    vector<T> values;

public:
    void add(T value) {
        values.push_back(value);
    }

    T sum() const {
        return accumulate(values.begin(), values.end(), T{});
    }

    double average() const {
        if (values.empty()) return 0.0;
        return static_cast<double>(sum()) / values.size();
    }

    optional<T> maximum() const {
        if (values.empty()) return nullopt;
        return *max_element(values.begin(), values.end());
    }

    template<typename Predicate>
    vector<T> filter(Predicate predicate) const {
        vector<T> result;

        copy_if(values.begin(), values.end(),
                back_inserter(result), predicate);

        return result;
    }
};

// ==========================================
// 2. OPERATOR OVERLOADING
// ==========================================

class BigNumber {
    int64_t value;

public:
    explicit BigNumber(int64_t v = 0) : value(v) {}

    BigNumber operator+(const BigNumber& other) const {
        return BigNumber(value + other.value);
    }

    BigNumber operator*(const BigNumber& other) const {
        return BigNumber(value * other.value);
    }

    bool operator<(const BigNumber& other) const {
        return value < other.value;
    }

    bool operator==(const BigNumber& other) const {
        return value == other.value;
    }

    int64_t get() const {
        return value;
    }

    friend ostream& operator<<(ostream& os,
                               const BigNumber& n) {
        return os << n.value;
    }
};

// ==========================================
// 3. EXPRESSION TREE USING VARIANT
// ==========================================

struct Literal {
    double value;
};

struct BinaryExpr;

using Expr = variant<
    Literal,
    shared_ptr<BinaryExpr>
>;

struct BinaryExpr {
    char operation;
    Expr left;
    Expr right;
};

class ExpressionEvaluator {
public:
    static double evaluate(const Expr& expr) {

        return visit([](const auto& node) -> double {

            using T = decay_t<decltype(node)>;

            if constexpr (is_same_v<T, Literal>) {
                return node.value;
            }
            else {
                double lhs = evaluate(node->left);
                double rhs = evaluate(node->right);

                switch (node->operation) {
                    case '+': return lhs + rhs;
                    case '-': return lhs - rhs;
                    case '*': return lhs * rhs;

                    case '/':
                        if (rhs == 0.0)
                            throw runtime_error("Division by zero");

                        return lhs / rhs;

                    default:
                        throw runtime_error("Invalid operator");
                }
            }

        }, expr);
    }
};

// ==========================================
// 4. CUSTOM EXCEPTION
// ==========================================

class GraphException : public runtime_error {
public:
    explicit GraphException(const string& message)
        : runtime_error(message) {}
};

// ==========================================
// 5. POLYMORPHISM AND SMART POINTERS
// ==========================================

class Task {
protected:
    int id;
    string name;

public:
    Task(int i, string n)
        : id(i), name(move(n)) {}

    virtual ~Task() = default;

    virtual int execute() const = 0;

    virtual string describe() const {
        return name;
    }

    int getId() const {
        return id;
    }
};

class ComputeTask : public Task {
    int workload;

public:
    ComputeTask(int id, string name, int w)
        : Task(id, move(name)), workload(w) {}

    int execute() const override {
        return workload * workload;
    }
};

class AggregateTask : public Task {
    vector<int> data;

public:
    AggregateTask(int id, string name, vector<int> d)
        : Task(id, move(name)), data(move(d)) {}

    int execute() const override {
        return accumulate(data.begin(), data.end(), 0);
    }
};

// ==========================================
// 6. GENERIC DEPENDENCY GRAPH
// ==========================================

class DependencyGraph {

    unordered_map<int, vector<pair<int, int>>> adjacency;

    unordered_map<int, shared_ptr<Task>> tasks;

public:

    void addTask(shared_ptr<Task> task) {
        int id = task->getId();

        if (tasks.contains(id))
            throw GraphException("Duplicate task ID");

        tasks[id] = move(task);
        adjacency[id];
    }

    void addDependency(int from, int to, int weight) {

        if (!tasks.contains(from) || !tasks.contains(to))
            throw GraphException("Unknown task");

        if (weight < 0)
            throw GraphException("Negative edge weight");

        adjacency[from].push_back({to, weight});
    }

    // Dijkstra shortest path

    unordered_map<int, int64_t> shortestPaths(int source) const {

        if (!tasks.contains(source))
            throw GraphException("Invalid source");

        constexpr int64_t INF =
            numeric_limits<int64_t>::max();

        unordered_map<int, int64_t> distance;

        for (const auto& [id, task] : tasks)
            distance[id] = INF;

        using State = pair<int64_t, int>;

        priority_queue<
            State,
            vector<State>,
            greater<State>
        > pq;

        distance[source] = 0;
        pq.push({0, source});

        while (!pq.empty()) {

            auto [currentDistance, u] = pq.top();
            pq.pop();

            if (currentDistance != distance[u])
                continue;

            for (const auto& [v, weight] : adjacency.at(u)) {

                if (currentDistance >
                    INF - static_cast<int64_t>(weight))
                    throw GraphException("Distance overflow");

                int64_t candidate =
                    currentDistance + weight;

                if (candidate < distance[v]) {
                    distance[v] = candidate;
                    pq.push({candidate, v});
                }
            }
        }

        return distance;
    }

    // Topological sorting using Kahn's algorithm

    vector<int> topologicalSort() const {

        unordered_map<int, int> indegree;

        for (const auto& [id, task] : tasks)
            indegree[id] = 0;

        for (const auto& [u, edges] : adjacency) {
            for (const auto& [v, weight] : edges)
                indegree[v]++;
        }

        priority_queue<
            int,
            vector<int>,
            greater<int>
        > ready;

        for (const auto& [id, degree] : indegree) {
            if (degree == 0)
                ready.push(id);
        }

        vector<int> order;

        while (!ready.empty()) {

            int u = ready.top();
            ready.pop();

            order.push_back(u);

            for (const auto& [v, weight] : adjacency.at(u)) {

                if (--indegree[v] == 0)
                    ready.push(v);
            }
        }

        if (order.size() != tasks.size())
            throw GraphException("Dependency cycle detected");

        return order;
    }

    int64_t executeAll() const {

        auto order = topologicalSort();

        int64_t total = 0;

        for (int id : order) {
            total += tasks.at(id)->execute();
        }

        return total;
    }

    void printTasks() const {

        vector<int> ids;

        for (const auto& [id, task] : tasks)
            ids.push_back(id);

        sort(ids.begin(), ids.end());

        for (int id : ids) {
            cout << id << ": "
                 << tasks.at(id)->describe()
                 << " = "
                 << tasks.at(id)->execute()
                 << '\n';
        }
    }
};

// ==========================================
// 7. BITWISE FLAGS
// ==========================================

enum class Permission : uint8_t {
    Read    = 1,
    Write   = 2,
    Execute = 4
};

constexpr uint8_t operator|(
    Permission a, Permission b) {

    return static_cast<uint8_t>(a) |
           static_cast<uint8_t>(b);
}

bool hasPermission(uint8_t flags, Permission p) {

    return (flags & static_cast<uint8_t>(p)) != 0;
}

// ==========================================
// 8. MOVE SEMANTICS AND RESOURCE MANAGEMENT
// ==========================================

class ResourceBuffer {

    unique_ptr<int[]> data;
    size_t size;

public:

    explicit ResourceBuffer(size_t n)
        : data(make_unique<int[]>(n)), size(n) {

        iota(data.get(), data.get() + size, 1);
    }

    ResourceBuffer(const ResourceBuffer& other)
        : data(make_unique<int[]>(other.size)),
          size(other.size) {

        copy(other.data.get(),
             other.data.get() + size,
             data.get());
    }

    ResourceBuffer(ResourceBuffer&& other) noexcept
        : data(move(other.data)),
          size(exchange(other.size, 0)) {}

    ResourceBuffer& operator=(ResourceBuffer&& other) noexcept {

        if (this != &other) {
            data = move(other.data);
            size = exchange(other.size, 0);
        }

        return *this;
    }

    ResourceBuffer& operator=(const ResourceBuffer& other) {

        if (this != &other) {
            ResourceBuffer temp(other);
            swap(data, temp.data);
            swap(size, temp.size);
        }

        return *this;
    }

    int64_t checksum() const {

        if (!data || size == 0)
            return 0;

        return accumulate(
            data.get(),
            data.get() + size,
            int64_t{0}
        );
    }

    size_t getSize() const {
        return size;
    }
};

// ==========================================
// 9. MAIN TEST EXECUTION
// ==========================================

int main() {

    cout << "===== C++20 MIGRATION STRESS TEST =====\n\n";

    // Test 1: Generic templates

    Statistics<int> stats;

    for (int x : {10, 20, 30, 40, 50})
        stats.add(x);

    cout << "[1] Statistics\n";
    cout << "Sum: " << stats.sum() << '\n';
    cout << "Average: " << stats.average() << '\n';
    cout << "Maximum: " << *stats.maximum() << '\n';

    auto filtered = stats.filter(
        [](int x) { return x > 25; }
    );

    cout << "Filtered count: " << filtered.size() << "\n\n";

    // Test 2: Operator overloading

    BigNumber a(120);
    BigNumber b(30);

    cout << "[2] Operator Overloading\n";
    cout << "Addition: " << (a + b) << '\n';
    cout << "Multiplication: " << (a * b) << "\n\n";

    // Test 3: Recursive expression evaluation
    //
    // (10 + 5) * (20 - 4) / 2 = 120

    Expr expression = make_shared<BinaryExpr>(
        BinaryExpr{
            '/',
            Expr(make_shared<BinaryExpr>(
                BinaryExpr{
                    '*',
                    Expr(make_shared<BinaryExpr>(
                        BinaryExpr{
                            '+',
                            Literal{10},
                            Literal{5}
                        }
                    )),
                    Expr(make_shared<BinaryExpr>(
                        BinaryExpr{
                            '-',
                            Literal{20},
                            Literal{4}
                        }
                    ))
                }
            )),
            Literal{2}
        }
    );

    cout << "[3] Expression Evaluation\n";
    cout << "Result: "
         << ExpressionEvaluator::evaluate(expression)
         << "\n\n";

    // Test 4: Dependency graph

    DependencyGraph graph;

    graph.addTask(
        make_shared<ComputeTask>(1, "Compilation", 10)
    );

    graph.addTask(
        make_shared<ComputeTask>(2, "Optimization", 20)
    );

    graph.addTask(
        make_shared<AggregateTask>(
            3, "Validation", vector<int>{10, 20, 30}
        )
    );

    graph.addTask(
        make_shared<ComputeTask>(4, "Deployment", 5)
    );

    graph.addTask(
        make_shared<AggregateTask>(
            5, "Monitoring", vector<int>{5, 10, 15}
        )
    );

    graph.addDependency(1, 2, 4);
    graph.addDependency(1, 3, 2);
    graph.addDependency(2, 4, 3);
    graph.addDependency(3, 4, 1);
    graph.addDependency(4, 5, 6);

    cout << "[4] Dependency Graph\n";

    graph.printTasks();

    cout << "Execution total: "
         << graph.executeAll()
         << "\n\n";

    // Test 5: Dijkstra shortest paths

    cout << "[5] Shortest Paths\n";

    auto distances = graph.shortestPaths(1);

    vector<int> sortedIds = {1, 2, 3, 4, 5};

    for (int id : sortedIds) {

        cout << "1 -> " << id << " = ";

        if (distances.at(id) ==
            numeric_limits<int64_t>::max()) {
            cout << "INF\n";
        }
        else {
            cout << distances.at(id) << '\n';
        }
    }

    cout << '\n';

    // Test 6: Topological sorting

    cout << "[6] Topological Ordering\n";

    auto order = graph.topologicalSort();

    for (int id : order)
        cout << id << ' ';

    cout << "\n\n";

    // Test 7: Bitwise permissions

    cout << "[7] Permissions\n";

    uint8_t permissions =
        Permission::Read | Permission::Write;

    cout << boolalpha;
    cout << "Read: "
         << hasPermission(permissions, Permission::Read)
         << '\n';

    cout << "Write: "
         << hasPermission(permissions, Permission::Write)
         << '\n';

    cout << "Execute: "
         << hasPermission(permissions, Permission::Execute)
         << "\n\n";

    // Test 8: Copy and move semantics

    cout << "[8] Resource Management\n";

    ResourceBuffer original(100);

    ResourceBuffer copied = original;

    ResourceBuffer moved = move(copied);

    cout << "Original checksum: "
         << original.checksum() << '\n';

    cout << "Moved checksum: "
         << moved.checksum() << '\n';

    cout << "Moved-from size: "
         << copied.getSize() << '\n';

    cout << '\n';

    // Test 9: Exception handling

    cout << "[9] Exception Handling\n";

    try {

        Expr invalid = make_shared<BinaryExpr>(
            BinaryExpr{
                '/',
                Literal{100},
                Literal{0}
            }
        );

        cout << ExpressionEvaluator::evaluate(invalid);

    }
    catch (const runtime_error& e) {
        cout << "Caught exception: "
             << e.what() << '\n';
    }

    cout << "\n===== ALL TESTS COMPLETED =====\n";

    return 0;
}
