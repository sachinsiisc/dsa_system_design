# 03 — Spring MVC & REST APIs

---

## 1. Request Flow (must know end-to-end)

```
HTTP Request
  → DispatcherServlet (front controller — single entry point)
    → HandlerMapping (finds which controller method handles this URL)
      → HandlerAdapter (invokes the method)
        → @Controller method runs
          → returns data / ResponseEntity
        → HttpMessageConverter (serializes to JSON via Jackson)
  → HTTP Response (JSON)
```

---

## 2. Core Annotations

```java
@RestController          // = @Controller + @ResponseBody (return value → JSON)
@RequestMapping("/api/v1/orders")  // base path for all methods in this class

@GetMapping("/{id}")     // GET /api/v1/orders/{id}
@PostMapping             // POST /api/v1/orders
@PutMapping("/{id}")     // PUT  /api/v1/orders/{id}
@DeleteMapping("/{id}")  // DELETE /api/v1/orders/{id}
@PatchMapping("/{id}")   // PATCH /api/v1/orders/{id}
```

---

## 3. Full REST Controller Example

```java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService orderService;

    // Constructor injection
    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    // GET /api/v1/orders?status=PENDING&page=0&size=20
    @GetMapping
    public ResponseEntity<Page<OrderDTO>> getOrders(
            @RequestParam(defaultValue = "PENDING") String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        Pageable pageable = PageRequest.of(page, size, Sort.by("createdAt").descending());
        return ResponseEntity.ok(orderService.findByStatus(status, pageable));
    }

    // GET /api/v1/orders/123
    @GetMapping("/{id}")
    public ResponseEntity<OrderDTO> getOrder(@PathVariable Long id) {
        return orderService.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    // POST /api/v1/orders
    @PostMapping
    public ResponseEntity<OrderDTO> createOrder(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderDTO created = orderService.create(request);
        URI location = URI.create("/api/v1/orders/" + created.getId());
        return ResponseEntity.created(location).body(created);
    }

    // PUT /api/v1/orders/123
    @PutMapping("/{id}")
    public ResponseEntity<OrderDTO> updateOrder(
            @PathVariable Long id,
            @Valid @RequestBody UpdateOrderRequest request) {

        return ResponseEntity.ok(orderService.update(id, request));
    }

    // DELETE /api/v1/orders/123
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteOrder(@PathVariable Long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

---

## 4. Input Annotations

| Annotation | Where | What |
|-----------|-------|------|
| `@PathVariable` | `/orders/{id}` URL segment | Extracts `id` from URL |
| `@RequestParam` | `/orders?page=1` | Query string parameter |
| `@RequestBody` | POST/PUT body | Deserializes JSON body |
| `@RequestHeader` | HTTP header | Extracts a header value |
| `@CookieValue` | Cookie | Extracts cookie |

---

## 5. Validation

```java
// DTO
public class CreateOrderRequest {

    @NotNull
    @NotBlank
    private String productId;

    @Min(1)
    @Max(1000)
    private int quantity;

    @Email
    private String customerEmail;

    @Future
    private LocalDate deliveryDate;
}

// Controller
@PostMapping
public ResponseEntity<OrderDTO> create(@Valid @RequestBody CreateOrderRequest req) {
    // @Valid triggers validation — if fails → MethodArgumentNotValidException
}
```

### Handle validation errors globally
```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidation(
            MethodArgumentNotValidException ex) {

        Map<String, String> errors = new HashMap<>();
        ex.getBindingResult().getFieldErrors()
            .forEach(e -> errors.put(e.getField(), e.getDefaultMessage()));
        return ResponseEntity.badRequest().body(errors);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<String> handleNotFound(OrderNotFoundException ex) {
        return ResponseEntity.notFound().build();
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handleGeneral(Exception ex) {
        return ResponseEntity.internalServerError().body("Something went wrong");
    }
}
```

---

## 6. `ResponseEntity` — Full Control Over Response

```java
// 200 OK with body
return ResponseEntity.ok(dto);

// 201 Created with Location header
return ResponseEntity.created(URI.create("/api/orders/" + id)).body(dto);

// 204 No Content
return ResponseEntity.noContent().build();

// 404 Not Found
return ResponseEntity.notFound().build();

// 400 Bad Request with message
return ResponseEntity.badRequest().body("Invalid input");

// Custom status + headers
return ResponseEntity.status(HttpStatus.ACCEPTED)
    .header("X-Request-ID", requestId)
    .body(dto);
```

---

## 7. Filters vs Interceptors

| | Filter | Interceptor |
|---|---|---|
| Layer | Servlet level (before Spring) | Spring MVC level |
| Access to | Raw request/response | Handler, ModelAndView |
| Use for | Auth tokens, CORS, logging | Pre/post controller logic |
| Interface | `javax.servlet.Filter` | `HandlerInterceptor` |

### Filter example (JWT auth check)
```java
@Component
public class JwtFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest req,
                                    HttpServletResponse res,
                                    FilterChain chain)
            throws ServletException, IOException {

        String token = req.getHeader("Authorization");
        if (token == null || !validateToken(token)) {
            res.setStatus(HttpStatus.UNAUTHORIZED.value());
            return;
        }
        chain.doFilter(req, res);
    }
}
```

### Interceptor example (logging)
```java
@Component
public class LoggingInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) {
        System.out.println("→ " + req.getMethod() + " " + req.getRequestURI());
        return true; // true = continue, false = abort
    }

    @Override
    public void afterCompletion(HttpServletRequest req, HttpServletResponse res,
                                Object handler, Exception ex) {
        System.out.println("← " + res.getStatus());
    }
}

// Register
@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new LoggingInterceptor())
                .addPathPatterns("/api/**");
    }
}
```

---

## 8. CORS

```java
// Controller level
@CrossOrigin(origins = "https://myfrontend.com")
@RestController

// Global
@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://myfrontend.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .allowedHeaders("*")
            .allowCredentials(true);
    }
}
```

---

## Interview Q&A — REST

**Q: What is DispatcherServlet?**
A: The front controller in Spring MVC. All HTTP requests go through it first. It delegates to the right controller method using HandlerMapping, then serializes the response using HttpMessageConverter.

**Q: Difference between `@Controller` and `@RestController`?**
A: `@RestController = @Controller + @ResponseBody`. With `@Controller`, you return view names (for MVC/Thymeleaf). With `@RestController`, the return value is serialized to JSON automatically.

**Q: How to handle exceptions globally?**
A: Use `@RestControllerAdvice` + `@ExceptionHandler`. One class handles errors for all controllers — keeps controllers clean.

**Q: Filter vs Interceptor?**
A: Filters are at the servlet container level, run before Spring. Interceptors are Spring-level, run around controller execution. Use filters for JWT/auth/CORS. Use interceptors for logging, audit trails.

**Q: How to validate request body?**
A: Add JSR-303 annotations (`@NotNull`, `@Email`, etc.) to the DTO, then add `@Valid` to the `@RequestBody` parameter. Spring automatically validates and throws `MethodArgumentNotValidException` on failure.
