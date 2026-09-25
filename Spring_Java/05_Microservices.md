# 05 — Microservices: Patterns, Discovery, Gateway, Circuit Breaker

---

## 1. Monolith vs Microservices

| | Monolith | Microservices |
|---|---|---|
| Deploy | One big artifact | Many small services |
| Scale | Scale everything | Scale individual services |
| Tech | One language/DB | Polyglot (each service chooses) |
| Failure | One bug crashes all | Failure isolated to one service |
| Complexity | Simple to start | Distributed system complexity |
| Communication | In-process method calls | HTTP / messaging |

**When to use microservices:** Large team, different scaling needs, need independent deployment.
**When NOT to:** Small team, early stage, simple domain.

---

## 2. Core Microservice Patterns

### Pattern 1: API Gateway
```
Client
  ↓
API Gateway (single entry point)
  ├── /orders  → Order Service
  ├── /users   → User Service
  └── /payment → Payment Service
```

**What API Gateway does:**
- Routing — forwards to correct service
- Auth/JWT validation (so each service doesn't need to)
- Rate limiting
- Load balancing
- SSL termination
- Request aggregation

**Spring Cloud Gateway:**
```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: lb://ORDER-SERVICE   # lb:// = load-balanced via Eureka
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
            - name: CircuitBreaker
              args:
                name: orderCB
                fallbackUri: forward:/fallback/orders
```

---

### Pattern 2: Service Discovery (Eureka)
```
Service A wants to call Service B.
Problem: Service B's IP/port can change (containers, scaling).
Solution: Service registry — all services register; caller looks up by name.
```

**Eureka Server:**
```java
@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApp { ... }
```

```yaml
# eureka server application.yml
server.port: 8761
eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
```

**Eureka Client (each microservice):**
```java
@SpringBootApplication
@EnableDiscoveryClient
public class OrderServiceApp { ... }
```

```yaml
spring.application.name: ORDER-SERVICE  # this is how it registers

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

---

### Pattern 3: Inter-service Communication

#### Synchronous: Feign Client (REST call by name)
```java
@FeignClient(name = "USER-SERVICE")  // name from Eureka
public interface UserServiceClient {

    @GetMapping("/api/users/{id}")
    UserDTO getUserById(@PathVariable Long id);
}

// Use in OrderService
@Service
public class OrderService {
    private final UserServiceClient userClient;

    public OrderDTO createOrder(CreateOrderRequest req) {
        UserDTO user = userClient.getUserById(req.getUserId()); // Feign handles HTTP
        // ...
    }
}
```

#### Asynchronous: Message Queue (RabbitMQ / Kafka)
```java
// Producer — OrderService
@Service
public class OrderService {
    private final RabbitTemplate rabbitTemplate;

    public void placeOrder(Order order) {
        // save order
        rabbitTemplate.convertAndSend("order.exchange", "order.placed",
            new OrderPlacedEvent(order.getId()));
    }
}

// Consumer — NotificationService (different service)
@Component
public class OrderEventListener {

    @RabbitListener(queues = "notification.queue")
    public void onOrderPlaced(OrderPlacedEvent event) {
        // send email
    }
}
```

---

### Pattern 4: Circuit Breaker (Resilience4j)

**The problem:** Service A calls Service B. B is slow/down. A threads pile up waiting → A crashes too (cascading failure).

**States:**
```
CLOSED → normal, requests go through
  ↓ (failure rate exceeds threshold, e.g. 50%)
OPEN → all requests FAIL FAST (no actual call) — fallback returned
  ↓ (after wait duration, e.g. 30s)
HALF-OPEN → let limited requests through to test
  ↓ (if success)
CLOSED → back to normal
```

```java
@Service
public class OrderService {

    private final UserServiceClient userClient;

    @CircuitBreaker(name = "userService", fallbackMethod = "getUserFallback")
    @Retry(name = "userService")
    @TimeLimiter(name = "userService")
    public UserDTO getUser(Long userId) {
        return userClient.getUserById(userId);
    }

    // Fallback method — same signature + Throwable
    public UserDTO getUserFallback(Long userId, Throwable t) {
        return UserDTO.defaultUser(userId); // return safe default
    }
}
```

```yaml
resilience4j:
  circuitbreaker:
    instances:
      userService:
        failure-rate-threshold: 50        # open if 50% of calls fail
        wait-duration-in-open-state: 30s
        sliding-window-size: 10           # last 10 calls
  retry:
    instances:
      userService:
        max-attempts: 3
        wait-duration: 500ms
  timelimiter:
    instances:
      userService:
        timeout-duration: 2s
```

---

### Pattern 5: Saga Pattern (Distributed Transactions)

**Problem:** How to maintain consistency across services without distributed transactions?
```
PlaceOrder:
  1. Create Order (OrderService)
  2. Reserve Inventory (InventoryService)
  3. Charge Payment (PaymentService)
  4. Send Confirmation (NotificationService)
```

**Choreography Saga (event-driven):**
```
OrderService → publishes OrderCreated event
  → InventoryService listens → reserves stock → publishes StockReserved
    → PaymentService listens → charges card → publishes PaymentCharged
      → NotificationService sends email

If PaymentService FAILS:
  → publishes PaymentFailed event
    → InventoryService listens → releases stock (compensating transaction)
      → OrderService listens → cancels order
```

**Orchestration Saga (central coordinator):**
```
SagaOrchestrator:
  1. call OrderService.create()
  2. call InventoryService.reserve()
  3. call PaymentService.charge()  ← fails
  4. call InventoryService.release() (compensate)
  5. call OrderService.cancel() (compensate)
```

---

### Pattern 6: Config Server

Centralised configuration for all services.

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApp { ... }
```

```yaml
# config server
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/myorg/config-repo
```

Each service pulls config from config server at startup:
```yaml
# bootstrap.yml in each service
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://config-server:8888
```

---

## 3. Spring Cloud Stack Summary

| Problem | Spring Cloud Component |
|---------|----------------------|
| Service Registry | Eureka Server |
| Client-side load balancing | Spring Cloud LoadBalancer |
| HTTP client between services | Feign Client |
| API Gateway | Spring Cloud Gateway |
| Circuit Breaker | Resilience4j |
| Centralized config | Spring Cloud Config |
| Distributed tracing | Sleuth + Zipkin |
| Message-based communication | Spring Cloud Stream (Kafka/Rabbit) |

---

## 4. Distributed Tracing

```
Request: A → B → C
Each service generates logs — how to correlate across services?
```

**Sleuth** adds trace ID + span ID to every log automatically:
```
[order-service, traceId=abc123, spanId=111] Processing order
[user-service,  traceId=abc123, spanId=222] Fetching user     ← same trace!
[payment-service, traceId=abc123, spanId=333] Charging card
```

**Zipkin** provides UI to view full request journey across services.

---

## 5. Design Principles

### 12-Factor App (know these)
1. Codebase — one codebase, many deploys
2. Dependencies — explicitly declared
3. Config — stored in environment (not code)
4. Backing services — treat as attached resources
5. Build/release/run — strict separation
6. Processes — stateless, share-nothing
7. Port binding — self-contained
8. Concurrency — scale via processes
9. Disposability — fast startup, graceful shutdown
10. Dev/prod parity — keep environments similar
11. Logs — treat as event streams
12. Admin processes — run as one-off tasks

---

## Interview Q&A — Microservices

**Q: What is an API Gateway?**
A: Single entry point for all clients. Handles routing, auth, rate limiting, SSL, load balancing. Clients talk to one address; the gateway routes to the right service. Prevents each service from needing its own auth logic.

**Q: How do microservices discover each other?**
A: Service Registry (Eureka). Each service registers on startup with its name/IP/port. To call another service, you look it up by name — no hardcoded IPs. Spring Cloud LoadBalancer picks an instance.

**Q: What is a Circuit Breaker?**
A: Prevents cascading failures. When a downstream service fails repeatedly, the circuit "opens" and all subsequent calls fail fast (no actual network call). After a wait period, it goes to HALF-OPEN to test recovery. Implements the states: CLOSED → OPEN → HALF-OPEN → CLOSED.

**Q: How to handle distributed transactions in microservices?**
A: Use the Saga pattern — no two-phase commit across services. Either Choreography (event-driven, each service reacts to events and publishes compensating events on failure) or Orchestration (central saga orchestrator coordinates steps and rollbacks).

**Q: Feign vs RestTemplate?**
A: Feign is declarative — define an interface with annotations, Spring generates the implementation. RestTemplate is imperative — you write the HTTP call code manually. Feign integrates with Eureka, Ribbon, and Circuit Breaker automatically. RestTemplate is being replaced by WebClient (reactive).

**Q: What happens when Config Server is down at startup?**
A: Service fails to start — by default it can't load its config. Use `spring.cloud.config.fail-fast=true` and set up Resilience4j retry for config fetch. Or use local fallback configs.

**Q: Synchronous vs Asynchronous between services?**
A: Synchronous (Feign/HTTP): simpler, immediate response, creates coupling and failure propagation risk. Asynchronous (Kafka/RabbitMQ): decoupled, resilient, eventual consistency, but harder to debug and no immediate response.
