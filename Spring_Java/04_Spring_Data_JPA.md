# 04 — Spring Data JPA: Repositories, JPQL, Transactions

---

## 1. JPA in 60 seconds

**JPA** = Java Persistence API — standard spec for ORM (Object-Relational Mapping)
**Hibernate** = JPA implementation Spring Boot uses by default
**Spring Data JPA** = adds Repository layer on top — zero-boilerplate CRUD

```
Your code → Repository interface
             ↓
         Spring Data (generates implementation)
             ↓
          Hibernate (translates to SQL)
             ↓
           Database
```

---

## 2. Entity

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY) // auto-increment PK
    private Long id;

    @Column(name = "customer_email", nullable = false, length = 255)
    private String customerEmail;

    @Enumerated(EnumType.STRING)  // store as "PENDING", not 0/1
    private OrderStatus status;

    @CreationTimestamp               // auto-set on insert
    private LocalDateTime createdAt;

    @UpdateTimestamp                 // auto-set on update
    private LocalDateTime updatedAt;

    @ManyToOne(fetch = FetchType.LAZY)  // always LAZY for @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();
}
```

---

## 3. Repository

```java
// Extend JpaRepository — get CRUD for free
public interface OrderRepository extends JpaRepository<Order, Long> {

    // --- Derived queries (Spring generates SQL from method name) ---
    List<Order> findByStatus(OrderStatus status);

    List<Order> findByCustomerEmailAndStatus(String email, OrderStatus status);

    Optional<Order> findTopByCustomerEmailOrderByCreatedAtDesc(String email);

    long countByStatus(OrderStatus status);

    boolean existsByCustomerEmail(String email);

    // --- JPQL (object-oriented query) ---
    @Query("SELECT o FROM Order o WHERE o.status = :status AND o.createdAt > :since")
    List<Order> findRecentByStatus(@Param("status") OrderStatus status,
                                   @Param("since") LocalDateTime since);

    // --- Native SQL ---
    @Query(value = "SELECT * FROM orders WHERE customer_id = ?1 LIMIT 10",
           nativeQuery = true)
    List<Order> findTopTenByCustomer(Long customerId);

    // --- Update query ---
    @Modifying
    @Query("UPDATE Order o SET o.status = :status WHERE o.id = :id")
    int updateStatus(@Param("id") Long id, @Param("status") OrderStatus status);

    // --- Pagination ---
    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

### Using the repository
```java
@Service
public class OrderService {

    private final OrderRepository orderRepo;

    public OrderService(OrderRepository orderRepo) {
        this.orderRepo = orderRepo;
    }

    public Page<OrderDTO> findByStatus(String status, Pageable pageable) {
        return orderRepo.findByStatus(OrderStatus.valueOf(status), pageable)
                        .map(OrderMapper::toDTO);
    }

    public OrderDTO create(CreateOrderRequest req) {
        Order order = new Order();
        order.setCustomerEmail(req.getEmail());
        order.setStatus(OrderStatus.PENDING);
        // set items...
        Order saved = orderRepo.save(order);
        return OrderMapper.toDTO(saved);
    }
}
```

---

## 4. Relationships

### @OneToMany / @ManyToOne (most common)
```java
// Parent
@Entity
public class Customer {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer",  // "customer" field in Order
               cascade = CascadeType.ALL,
               fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();
}

// Child — owns the FK
@Entity
public class Order {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

### Fetch types
| | LAZY | EAGER |
|---|---|---|
| When loaded | Only when accessed | Always with parent |
| Default for | @OneToMany, @ManyToMany | @ManyToOne, @OneToOne |
| Recommendation | Always LAZY — load explicitly when needed | Avoid |

### CascadeType
```java
CascadeType.ALL         // all operations cascade (persist, merge, remove...)
CascadeType.PERSIST     // when parent saved, children saved too
CascadeType.MERGE       // when parent updated, children updated
CascadeType.REMOVE      // when parent deleted, children deleted
orphanRemoval = true    // remove child from DB when removed from collection
```

---

## 5. The N+1 Problem (critical interview topic)

**Problem:**
```java
// Loads 100 orders — 1 query
List<Order> orders = orderRepo.findAll();

// For EACH order, Hibernate fires a separate query to load customer — 100 queries!
orders.forEach(o -> System.out.println(o.getCustomer().getName()));
// Total: 1 + 100 = 101 queries — N+1!
```

**Fix 1: JOIN FETCH in JPQL**
```java
@Query("SELECT o FROM Order o JOIN FETCH o.customer WHERE o.status = 'PENDING'")
List<Order> findPendingWithCustomer();
// Result: 1 query with JOIN — loads orders + customers together
```

**Fix 2: `@EntityGraph`**
```java
@EntityGraph(attributePaths = {"customer", "items"})
List<Order> findByStatus(OrderStatus status);
// Spring adds JOIN for specified paths automatically
```

---

## 6. `@Transactional` — Deep Dive

```java
@Service
@Transactional  // default: applies to all public methods
public class OrderService {

    // REQUIRED (default): use existing tx, or start new one
    @Transactional(propagation = Propagation.REQUIRED)
    public void placeOrder(Order order) { ... }

    // REQUIRES_NEW: always start a new tx (suspends existing)
    // Use for: audit logging — should save even if main tx rolls back
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void auditLog(String action) { ... }

    // NEVER: throw exception if called inside a tx
    @Transactional(propagation = Propagation.NEVER)
    public void readOnly() { ... }

    // READ-ONLY: optimization for reads — no dirty checking
    @Transactional(readOnly = true)
    public List<Order> getOrders() { ... }

    // ROLLBACK on specific exception (default: RuntimeException)
    @Transactional(rollbackFor = Exception.class)
    public void riskyOperation() throws Exception { ... }
}
```

### Propagation types summary
| Propagation | Behaviour |
|-------------|-----------|
| `REQUIRED` | Join existing tx; start new if none. Default. |
| `REQUIRES_NEW` | Always new tx; suspends current. |
| `NESTED` | Savepoint inside current tx; partial rollback possible. |
| `SUPPORTS` | Join if exists; no tx if none. |
| `NOT_SUPPORTED` | Suspend current tx; run without tx. |
| `MANDATORY` | Must have existing tx; else exception. |
| `NEVER` | Must NOT have tx; else exception. |

### Common `@Transactional` pitfall — self-invocation
```java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        sendEmail();  // ❌ @Transactional on sendEmail() is IGNORED!
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void sendEmail() { ... }
}
```
**Why?** Spring's proxy wraps the bean. Self-calls bypass the proxy — no AOP, no transaction.
**Fix:** Inject self or extract to another bean.

---

## 7. Projection — Select only needed fields

```java
// Interface projection
public interface OrderSummary {
    Long getId();
    String getCustomerEmail();
    OrderStatus getStatus();
}

public interface OrderRepository extends JpaRepository<Order, Long> {
    List<OrderSummary> findByStatus(OrderStatus status); // returns only 3 fields
}
```

---

## Interview Q&A — JPA

**Q: What is the N+1 problem?**
A: When loading a list of entities (1 query), then accessing a lazy-loaded association for each entity triggers N additional queries. Fix with JOIN FETCH or @EntityGraph.

**Q: EAGER vs LAZY fetch?**
A: EAGER loads related entities immediately with the parent. LAZY loads them only when accessed. Always use LAZY — EAGER causes unnecessary data loading and can cause performance issues.

**Q: `@Transactional` propagation REQUIRED vs REQUIRES_NEW?**
A: REQUIRED (default) reuses an existing transaction or starts a new one. REQUIRES_NEW always starts a fresh transaction, suspending any existing one. Use REQUIRES_NEW for audit logs that must persist even if the main transaction rolls back.

**Q: What is `orphanRemoval`?**
A: If an entity is removed from a collection (`parent.getChildren().remove(child)`), it is also deleted from the database. Without it, the child becomes orphaned with a null FK.

**Q: How does `@Modifying` work?**
A: Used with `@Query` for UPDATE/DELETE JPQL statements. Without it, Spring Data expects a SELECT. Also needs `@Transactional`.
