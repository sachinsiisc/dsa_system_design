# 01 — Spring Core: IoC, DI, Beans, AOP

---

## 1. IoC — Inversion of Control

**The idea:** You don't create objects. Spring creates and manages them.
Without IoC: `UserService us = new UserService(new UserRepo());`
With IoC: Spring builds the graph, you just declare dependencies.

**The container:** `ApplicationContext` — holds all beans, wires them up.

```
Traditional:          IoC:
You → new Object()    Container → creates → injects → gives you
```

---

## 2. Dependency Injection (DI) — 3 Types

### Constructor Injection (preferred ✅)
```java
@Service
public class OrderService {
    private final PaymentService paymentService;

    // Spring injects via constructor
    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
```
**Why preferred:** immutable fields, easy to test (pass mock in constructor), fails fast at startup.

### Field Injection (avoid ❌)
```java
@Service
public class OrderService {
    @Autowired
    private PaymentService paymentService; // hidden dependency, hard to test
}
```

### Setter Injection (for optional deps)
```java
@Service
public class OrderService {
    private PaymentService paymentService;

    @Autowired
    public void setPaymentService(PaymentService ps) {
        this.paymentService = ps;
    }
}
```

---

## 3. Beans — Everything You Need to Know

### What is a Bean?
An object managed by the Spring container. Spring creates it, wires dependencies, manages lifecycle.

### Ways to define a Bean

**A) `@Component` family — for your own classes:**
```java
@Component   // generic
@Service     // service layer (same as @Component, just semantic)
@Repository  // DAO layer — also enables exception translation
@Controller  // MVC controller
@RestController // @Controller + @ResponseBody
```

**B) `@Bean` inside a `@Configuration` class — for third-party / complex setup:**
```java
@Configuration
public class AppConfig {

    @Bean
    public ObjectMapper objectMapper() {
        ObjectMapper om = new ObjectMapper();
        om.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        return om;
    }

    @Bean
    public RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

**When to use `@Bean` vs `@Component`:**
| | `@Component` | `@Bean` |
|---|---|---|
| For | Your own classes | Third-party classes or complex creation |
| Location | On the class | In `@Configuration` method |
| Control | Less | Full control over creation |

### Bean Scopes
```java
@Component
@Scope("singleton")   // default — one instance per container
@Scope("prototype")   // new instance every time it's injected
@Scope("request")     // one per HTTP request (web apps)
@Scope("session")     // one per HTTP session
```

### Bean Lifecycle
```
Container starts
  → Instantiate bean
  → Inject dependencies
  → @PostConstruct (your init code)
  → Bean is ready
  → ... app runs ...
  → @PreDestroy (your cleanup code)
  → Container shuts down
```

```java
@Component
public class CacheService {

    @PostConstruct
    public void init() {
        // load cache from DB
        System.out.println("Cache loaded");
    }

    @PreDestroy
    public void cleanup() {
        // flush, close connections
        System.out.println("Cache cleared");
    }
}
```

---

## 4. `@Autowired` — Resolving Beans

### By Type (default)
Spring finds bean of matching type. Fails if 0 or 2+ match.

### Multiple beans of same type → use `@Qualifier`
```java
@Component("fastPayment")
public class FastPaymentService implements PaymentService { }

@Component("slowPayment")
public class SlowPaymentService implements PaymentService { }

@Service
public class OrderService {
    private final PaymentService paymentService;

    public OrderService(@Qualifier("fastPayment") PaymentService ps) {
        this.paymentService = ps;
    }
}
```

### Or use `@Primary`
```java
@Component
@Primary   // default choice when multiple candidates
public class FastPaymentService implements PaymentService { }
```

---

## 5. AOP — Aspect-Oriented Programming

**The problem:** Logging, security, transactions, metrics — repeated in every method.
**AOP solution:** Extract cross-cutting concerns into an Aspect. Apply them declaratively.

### Core concepts
| Term | Meaning |
|------|---------|
| **Aspect** | The class holding the cross-cutting logic |
| **Advice** | When to run (`@Before`, `@After`, `@Around`) |
| **Pointcut** | Which methods to target (expression) |
| **Join Point** | The actual method execution |

### Example — Logging Aspect
```java
@Aspect
@Component
public class LoggingAspect {

    // target all methods in service package
    @Around("execution(* com.example.service.*.*(..))")
    public Object logExecutionTime(ProceedingJoinPoint joinPoint) throws Throwable {
        long start = System.currentTimeMillis();
        Object result = joinPoint.proceed(); // run the actual method
        long elapsed = System.currentTimeMillis() - start;
        System.out.println(joinPoint.getSignature() + " executed in " + elapsed + "ms");
        return result;
    }
}
```

### Advice types
```java
@Before("execution(* com.example.service.*.*(..))")
public void before(JoinPoint jp) { /* runs before method */ }

@After("execution(* com.example.service.*.*(..))")
public void after(JoinPoint jp) { /* runs after — always */ }

@AfterReturning(pointcut="...", returning="result")
public void afterReturn(Object result) { /* runs after success */ }

@AfterThrowing(pointcut="...", throwing="ex")
public void afterThrow(Exception ex) { /* runs on exception */ }

@Around("...")  // most powerful — can modify input/output, handle exceptions
public Object around(ProceedingJoinPoint pjp) throws Throwable { }
```

### Real use: Custom annotation + AOP
```java
// Define annotation
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Timed { }

// Apply on methods
@Timed
public void processOrder(Order o) { ... }

// Intercept in Aspect
@Around("@annotation(Timed)")
public Object timeIt(ProceedingJoinPoint pjp) throws Throwable {
    // measure time
}
```

---

## 6. `@Configuration` vs `@Component`

```java
@Configuration   // methods annotated with @Bean are proxied — singleton guaranteed
public class Config {
    @Bean public A a() { return new A(); }
    @Bean public B b() { return new B(a()); } // calls a() — gets SAME bean (proxied)
}

@Component       // no proxying — calling a() would create a NEW instance
public class Config {
    @Bean public A a() { return new A(); }
    @Bean public B b() { return new B(a()); } // NEW A created — probably a bug!
}
```

---

## Key Interview Q&A — Spring Core

**Q: What is IoC?**
A: Design principle where object creation and dependency wiring is delegated to a container (Spring's ApplicationContext) instead of being done manually in code.

**Q: Constructor vs field injection?**
A: Constructor injection is preferred — dependencies are explicit, object is always fully initialized, easy to unit test without Spring container.

**Q: `@Component` vs `@Bean`?**
A: `@Component` is on your class, Spring detects it via classpath scan. `@Bean` is in a `@Configuration` method, used for third-party classes or when you need custom creation logic.

**Q: What is AOP used for?**
A: Cross-cutting concerns — logging, transaction management (`@Transactional` is AOP under the hood), security, metrics, retry logic.

**Q: Singleton scope vs Prototype?**
A: Singleton — one instance per container, shared across all injection points. Prototype — new instance each time it's injected. Default is singleton.
