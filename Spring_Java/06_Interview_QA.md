# 06 — Spring & Microservices Interview Q&A — 60 Questions

---

## SECTION A: Spring Core (15 questions)

**1. What is the Spring IoC container?**
ApplicationContext — manages bean lifecycle, dependency injection, and configuration. It creates, configures, and wires all beans.

**2. How does Spring DI work?**
Spring reads your class, sees `@Autowired` (or constructor params), finds matching beans in the container, and injects them. No `new` needed.

**3. Constructor vs Field vs Setter injection — which is best and why?**
Constructor injection. Reasons: (1) Dependencies explicit in signature. (2) Object always fully initialized. (3) Easy to unit test — just pass mock via constructor. (4) Supports immutable (final) fields.

**4. What is `@Component`, and how does it differ from `@Service`, `@Repository`?**
All three are `@Component` specializations — they register a bean. Semantic difference: `@Service` marks business logic, `@Repository` enables JPA exception translation (converts DB exceptions to Spring's `DataAccessException`).

**5. `@Bean` vs `@Component`?**
`@Component` on YOUR class, detected by classpath scan. `@Bean` in a `@Configuration` method — used for third-party classes you can't annotate, or when you need custom creation logic.

**6. What is bean scope? What's the default?**
Scope = how many instances Spring creates. Default = `singleton` (one per container). Other scopes: `prototype` (new each time), `request`, `session` (web apps).

**7. Explain `@PostConstruct` and `@PreDestroy`.**
`@PostConstruct`: runs after DI is complete — use to initialize state (load cache, open connections). `@PreDestroy`: runs before bean is destroyed — use to clean up (flush, close).

**8. What is `@Configuration`? Why not just use `@Component` for config?**
`@Configuration` proxies the class so that `@Bean` methods calling other `@Bean` methods return the SAME singleton. With `@Component`, each call would create a new instance — breaking singleton guarantee.

**9. What is AOP and what is it used for in Spring?**
Aspect-Oriented Programming — separates cross-cutting concerns (logging, transactions, security, metrics) from business logic. `@Transactional` is AOP under the hood.

**10. What are the advice types in AOP?**
`@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`, `@Around`. `@Around` is most powerful — can modify input/output and handle exceptions.

**11. What is `@Qualifier`? When do you need it?**
When multiple beans of the same type exist, `@Qualifier("beanName")` tells Spring which one to inject. Alternative: mark one with `@Primary`.

**12. What does `@ComponentScan` do?**
Tells Spring which packages to scan for `@Component`, `@Service`, etc. `@SpringBootApplication` includes `@ComponentScan` for the current package and sub-packages.

**13. Can a singleton bean have a prototype-scoped dependency?**
Problem — yes, but the singleton holds one reference to the prototype (gets created once). Fix: use `ApplicationContext.getBean()` each time, or use `@Lookup` annotation.

**14. What is `ApplicationContext` vs `BeanFactory`?**
`BeanFactory` is the basic container (lazy init). `ApplicationContext` extends it — adds i18n, events, eager singleton init, `@PostConstruct`/`@PreDestroy`, AOP. Always use `ApplicationContext`.

**15. How does `@Value` work?**
Injects a value from `application.properties`. Supports SpEL: `@Value("${app.timeout:5000}")` — with default 5000 if property missing.

---

## SECTION B: Spring Boot (10 questions)

**16. What does `@SpringBootApplication` contain?**
`@Configuration + @EnableAutoConfiguration + @ComponentScan`. Marks entry point, enables auto-config, scans current package.

**17. How does auto-configuration work?**
Spring reads `AutoConfiguration.imports` file. Each config class has `@ConditionalOn*` conditions. If conditions pass and you haven't defined your own bean, it registers one. Your beans always override auto-config.

**18. What is a Spring Boot Starter?**
Curated dependency bundle — one `spring-boot-starter-web` gives you Spring MVC + Jackson + Tomcat at compatible versions. No manual version management.

**19. What is `application.yml` vs `application.properties`?**
Both configure Spring Boot. YAML allows nested structure — easier to read for complex config. Both work — pick one and be consistent.

**20. How do Spring Profiles work?**
`application-dev.yml` → active when `spring.profiles.active=dev`. Lets you have different DB URLs, log levels, etc. per environment.

**21. What is Spring Boot Actuator?**
Exposes production endpoints: `/health`, `/metrics`, `/info`, `/env`, `/beans`. Used by monitoring tools. Secure in prod — only expose `/health`.

**22. What is `@ConfigurationProperties`?**
Binds a prefix from `application.yml` to a POJO. Cleaner than many `@Value` annotations. Add `@EnableConfigurationProperties` or annotate the class with `@Component`.

**23. How to change the embedded server port?**
`server.port=9090` in `application.yml`. Or `-Dserver.port=9090` as JVM arg.

**24. What is Spring Boot DevTools?**
Auto-restarts app on code changes, disables caching for templates. Dev-only dependency.

**25. How to run code on Spring Boot startup?**
Implement `CommandLineRunner` or `ApplicationRunner` interface. Or use `@EventListener(ApplicationReadyEvent.class)`.

---

## SECTION C: Spring MVC / REST (10 questions)

**26. What is DispatcherServlet?**
Front controller. Every HTTP request goes through it. It routes to the right controller using HandlerMapping, invokes it via HandlerAdapter, then serializes response via HttpMessageConverter (Jackson for JSON).

**27. `@Controller` vs `@RestController`?**
`@RestController = @Controller + @ResponseBody`. `@Controller` returns view name (for Thymeleaf/JSP). `@RestController` serializes return value to JSON.

**28. How to handle exceptions globally?**
`@RestControllerAdvice` class with `@ExceptionHandler` methods. One place for all error handling.

**29. What is `@Valid` and how does validation work?**
JSR-303 annotations on DTO fields (`@NotNull`, `@Email`, `@Min`). `@Valid` on `@RequestBody` parameter triggers validation. Failure → `MethodArgumentNotValidException`.

**30. Filter vs Interceptor?**
Filter: servlet level, before Spring — for JWT auth, CORS, compression. Interceptor: Spring level, around controller — for logging, audit. Filter is more low-level.

**31. What is `ResponseEntity`?**
Wrapper that gives you control over HTTP status code, headers, and body. `ResponseEntity.ok(body)`, `ResponseEntity.created(uri).body(dto)`, `ResponseEntity.noContent().build()`.

**32. How to implement pagination?**
`Pageable` parameter in controller: `@RequestParam int page, int size → PageRequest.of(page, size)`. Pass to repository method returning `Page<T>`.

**33. What is CORS and how to configure it?**
Cross-Origin Resource Sharing — browser blocks JS from calling API on different domain. Enable with `@CrossOrigin` on controller or global `WebMvcConfigurer.addCorsMappings()`.

**34. How does `@PathVariable` differ from `@RequestParam`?**
`@PathVariable` extracts from URL path (`/orders/{id}`). `@RequestParam` extracts from query string (`/orders?page=1`). Path variable is required; request param can have defaults.

**35. What is content negotiation?**
Spring returns JSON or XML based on `Accept` header from client. Jackson handles JSON; add `jackson-dataformat-xml` for XML. `@RequestMapping(produces = "application/json")` restricts to JSON only.

---

## SECTION D: Spring Data JPA (10 questions)

**36. What is the difference between JPA, Hibernate, and Spring Data JPA?**
JPA = spec (interface). Hibernate = JPA implementation. Spring Data JPA = abstraction on top of JPA — provides Repository interface, generates queries from method names, zero boilerplate CRUD.

**37. What is the N+1 problem and how to fix it?**
Loading N entities triggers N extra queries for each lazy association. Fix: `JOIN FETCH` in JPQL or `@EntityGraph`. Never leave lazy associations without addressing N+1 in list queries.

**38. EAGER vs LAZY loading?**
EAGER loads the association immediately with the parent. LAZY loads only when accessed. Always use LAZY — EAGER can load the entire DB graph unintentionally.

**39. What does `@Transactional` do?**
Opens a DB transaction before the method, commits on success, rolls back on RuntimeException. Implemented via AOP proxy.

**40. Propagation REQUIRED vs REQUIRES_NEW?**
REQUIRED: join existing transaction or start new. REQUIRES_NEW: always new transaction, suspends current. Use REQUIRES_NEW for audit logs that must persist even if main transaction fails.

**41. Why does self-invocation break `@Transactional`?**
Spring wraps your bean in a proxy. External calls go through the proxy (AOP applied). Self-calls (`this.method()`) bypass the proxy — no transaction management.

**42. What is `@Modifying`?**
Required for UPDATE/DELETE JPQL queries in `@Query`. Tells Spring Data it's not a SELECT. Also needs `@Transactional`.

**43. What is `CascadeType.ALL` and `orphanRemoval`?**
`CascadeType.ALL`: all operations (save/delete/merge) cascade to children. `orphanRemoval=true`: if child removed from collection, it's deleted from DB.

**44. What is a Projection in Spring Data?**
Interface with only the fields you need. Repository returns `List<MyProjection>` instead of full entity — avoids loading unneeded columns.

**45. When to use `@Query` vs derived query methods?**
Derived methods (from name) for simple queries. `@Query` for complex joins, subqueries, or when method name would be unreadably long.

---

## SECTION E: Microservices (15 questions)

**46. What is an API Gateway?**
Single entry point for all clients. Routes to services, handles cross-cutting: auth, rate limiting, SSL, load balancing. Clients don't know service addresses.

**47. How do microservices discover each other?**
Service registry (Eureka). Services register with name on startup. Callers look up by name — no hardcoded IPs. Load balancer picks one instance.

**48. What is a Circuit Breaker and what are its states?**
Prevents cascading failures. CLOSED = normal. OPEN = all calls fail fast (downstream is down). HALF-OPEN = test with limited calls. Returns to CLOSED if healthy.

**49. Feign vs RestTemplate?**
Feign: declarative, define interface → Spring generates implementation. Integrates with Eureka and Circuit Breaker. RestTemplate: manual HTTP calls, imperative. Feign preferred for microservices.

**50. Synchronous vs asynchronous service communication?**
Sync (HTTP/Feign): simple, immediate, tight coupling, failure propagation. Async (Kafka/Rabbit): decoupled, resilient, eventual consistency, harder to debug.

**51. What is the Saga pattern?**
Manages distributed transactions without 2PC. Sequence of local transactions with compensating transactions on failure. Choreography (event-driven) or Orchestration (central coordinator).

**52. How to trace a request across multiple services?**
Distributed tracing — Sleuth adds trace ID + span ID to logs. All services pass trace ID in headers. Zipkin aggregates and visualises the call graph.

**53. What is Config Server?**
Centralised config service. All microservices pull their config from it at startup. Backed by Git. Change config without redeploying services (with `/actuator/refresh`).

**54. What is the Strangler Fig pattern?**
Migrating a monolith to microservices gradually. New functionality added as new microservice. Old functionality "strangled" one piece at a time. API gateway routes old → monolith, new → service.

**55. How to handle security in microservices?**
JWT at API Gateway — validate token once. Pass user identity (in header) to downstream services. Services trust the gateway. Don't validate JWT in every service.

**56. What is eventual consistency?**
In distributed systems, data across services is not immediately consistent — it becomes consistent "eventually" via events. Accept this; design for it (idempotent consumers, retry, deduplication).

**57. How to make a Kafka consumer idempotent?**
Unique event ID in each message. Consumer checks if ID already processed (in DB or Redis). If yes, skip. Prevents duplicate processing on retry.

**58. What is a Dead Letter Queue (DLQ)?**
Messages that fail processing after N retries go to DLQ. Prevents bad messages from blocking the queue. DLQ can be monitored and replayed after fixing the bug.

**59. Blue-Green vs Canary deployment?**
Blue-Green: two identical environments (blue=current, green=new). Switch traffic 100% at once. Easy rollback. Canary: route small % to new version, gradually increase if healthy. Less risky.

**60. What is a sidecar pattern?**
Attach a helper container to each microservice container (same pod in Kubernetes). Handles cross-cutting: logging, monitoring, service mesh (Envoy proxy). Service stays focused on business logic.
