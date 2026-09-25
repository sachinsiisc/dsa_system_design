# DSA + System Design — MAANG Interview Prep Repository
## Complete guide: Data Structures · Algorithms · HLD · LLD

---

## 📚 How to Use This Repo

This repo is structured for **active recall, not passive reading.**
Each topic has:
- `Theory.md` — full math, complexity proofs, worked examples, diagrams
- `problems.py` — 8-12 problems per topic with hints (attempt before looking at solution)
- `solutions.py` — complete solutions with step-by-step reasoning, all edge cases

---

## 🗓️ 12-Week MAANG Study Plan

| Week | Topic | Priority |
|------|-------|----------|
| 1 | Arrays, Strings, Hashing | 🔴 Critical |
| 2 | Sliding Window, Two Pointers, Binary Search | 🔴 Critical |
| 3 | Stack, Queue, Monotonic Stack | 🔴 Critical |
| 4 | Linked Lists, Trees, BST | 🔴 Critical |
| 5 | Graphs — BFS/DFS, Topological Sort | 🔴 Critical |
| 6 | Heap, Priority Queue, Intervals | 🔴 Critical |
| 7 | Dynamic Programming I (1D, 2D) | 🔴 Critical |
| 8 | DP II (Knapsack, LCS, Edit Distance) + Backtracking | 🔴 Critical |
| 9 | Trie, Bit Manipulation, Math Tricks | 🟡 Important |
| 10 | HLD Fundamentals + 4 core systems | 🔴 Critical |
| 11 | HLD — 8 more systems | 🔴 Critical |
| 12 | LLD — Design Patterns + 8 OOP problems | 🔴 Critical |

---

## 🗂️ Repository Layout

```
dsa_system_design/
│
├── DSA/
│   ├── 00_Patterns_Reference.md       ← START HERE: pattern recognition guide
│   ├── 01_Arrays_Strings/
│   ├── 02_Hashing/
│   ├── 03_Sliding_Window/
│   ├── 04_Two_Pointers/
│   ├── 05_Binary_Search/
│   ├── 06_Stack_Queue/
│   ├── 07_Linked_Lists/
│   ├── 08_Trees_Binary_Trees/
│   ├── 09_BST/
│   ├── 10_Graphs_BFS_DFS/
│   ├── 11_Topological_Sort/
│   ├── 12_Heap_Priority_Queue/
│   ├── 13_Dynamic_Programming/
│   ├── 14_Backtracking/
│   └── 15_Trie_Bit_Manipulation/
│
├── System_Design_HLD/
│   ├── 00_HLD_Framework.md            ← 7-step design framework
│   ├── 00_Fundamentals/               ← CAP, caching, databases, queues
│   ├── 01_URL_Shortener/
│   ├── 02_Rate_Limiter/
│   ├── 03_News_Feed/
│   ├── 04_Chat_System/
│   ├── 05_Video_Streaming/
│   ├── 06_Ride_Sharing/
│   ├── 07_Search_Typeahead/
│   ├── 08_Distributed_Cache/
│   ├── 09_Notification_System/
│   ├── 10_Payment_System/
│   ├── 11_Distributed_ID_Generator/
│   └── 12_Web_Crawler/
│
└── System_Design_LLD/
    ├── 00_LLD_Framework.md
    ├── 00_Design_Patterns/
    ├── 01_Parking_Lot/
    ├── 02_Elevator_System/
    ├── 03_Library_Management/
    ├── 04_Hotel_Booking/
    ├── 05_Chess_Game/
    ├── 06_Ride_Sharing_LLD/
    ├── 07_Movie_Ticket_Booking/
    └── 08_Food_Delivery/
```

---

## ⚡ Pattern Recognition Cheat Sheet (memorise this)

| Signal in problem | Pattern to reach for |
|-------------------|---------------------|
| Subarray / substring | Sliding window or prefix sum |
| Sorted array + O(n) | Two pointers |
| "K-th largest / smallest" | Heap (min-heap of size k) |
| Sorted + O(log n) | Binary search |
| "All combinations / permutations" | Backtracking |
| Graph with cycles | DFS with visited set |
| Shortest path unweighted | BFS |
| Shortest path weighted | Dijkstra |
| Task scheduling / dependency | Topological sort |
| Optimal substructure | DP |
| Prefix / autocomplete | Trie |
| Balance parens / nearest greater | Monotonic stack |
| O(1) lookup by value | HashMap |
| Sliding max / min | Monotonic deque |

---

## 🏆 MAANG Problem Frequency (based on reported interviews)

| Company | Favourite Topics |
|---------|-----------------|
| **Google** | Graphs, DP, Trees, System Design (scale) |
| **Meta** | Arrays, Graphs (social network), DP, Product sense |
| **Amazon** | Trees, DP, Arrays, LLD (OOP design), Leadership principles |
| **Apple** | Trees, Strings, System Design, Clean code |
| **Netflix** | System Design (streaming), DP, Graphs |
| **Microsoft** | Trees, DP, System Design, Coding style |
