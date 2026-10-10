package org.jeecg.maintenance;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.mgt.DefaultSessionStorageEvaluator;
import org.apache.shiro.mgt.DefaultSubjectDAO;
import org.apache.shiro.spring.security.interceptor.AuthorizationAttributeSourceAdvisor;
import org.apache.shiro.spring.web.ShiroFilterFactoryBean;
import org.apache.shiro.spring.web.ShiroUrlPathHelper;
import org.apache.shiro.web.filter.InvalidRequestFilter;
import org.apache.shiro.web.filter.mgt.FilterChainManager;
import org.apache.shiro.web.filter.mgt.NamedFilterList;
import org.apache.shiro.web.filter.mgt.PathMatchingFilterChainResolver;
import org.apache.shiro.web.mgt.DefaultWebSecurityManager;
import org.apache.shiro.web.servlet.AbstractShiroFilter;
import org.apache.shiro.web.util.WebUtils;
import org.apache.catalina.Container;
import org.apache.catalina.core.StandardContext;
import org.jeecg.JeecgApplication;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.jeecg.modules.shiro.authc.aop.JwtFilter;
import org.jeecg.modules.shiro.authc.aop.MediaJwtFilter;
import org.jeecg.modules.shiro.authc.aop.OptionalJwtFilter;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.embedded.tomcat.TomcatWebServer;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletContextInitializer;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.server.ErrorPage;
import org.springframework.boot.web.server.ErrorPageRegistrar;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import org.springframework.web.method.HandlerMethod;

import javax.servlet.DispatcherType;
import javax.servlet.Filter;
import javax.servlet.FilterRegistration;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.Proxy;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ConcurrentHashMap;

/** Test-only launcher; synthetic dispatch endpoints exist only in this short-lived context. */
public final class VerifyShiroMaintenance {
    private static final List<Map<String, Object>> checks = new ArrayList<>();
    private static final List<Map<String, Object>> observations = new ArrayList<>();
    private static final String ENTRY = "/maintenance-dispatch.js";
    private static final String PRIVATE = "/maintenance-private";
    private static final AtomicInteger privateExecutions = new AtomicInteger();
    private static final Map<DispatcherType, AtomicInteger> seen = new EnumMap<>(DispatcherType.class);
    private static final Map<String, Integer> initialErrors = new ConcurrentHashMap<>();

    private static void installTestServlets(ConfigurableApplicationContext context) {
        for (DispatcherType type : DispatcherType.values()) seen.put(type, new AtomicInteger());
        ServletContextInitializer initializer = servletContext -> {
            servletContext.addServlet("maintenance-public-dispatch", new HttpServlet() {
                @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws java.io.IOException, ServletException {
                    String mode = request.getParameter("mode");
                    if ("forward".equals(mode)) request.getRequestDispatcher(PRIVATE).forward(request, response);
                    else if ("include".equals(mode)) request.getRequestDispatcher(PRIVATE).include(request, response);
                    else if ("error".equals(mode)) response.sendError(418);
                    else response.getWriter().write("synthetic public entry");
                }
            }).addMapping(ENTRY);
            servletContext.addServlet("maintenance-private-target", new HttpServlet() {
                @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws java.io.IOException {
                    privateExecutions.incrementAndGet();
                    response.getWriter().write("PRIVATE_TARGET_EXECUTED");
                }
            }).addMapping(PRIVATE);
        };
        Filter observer = new Filter() {
            @Override public void init(javax.servlet.FilterConfig config) {}
            @Override public void destroy() {}
            @Override public void doFilter(javax.servlet.ServletRequest request, javax.servlet.ServletResponse response, javax.servlet.FilterChain chain) throws java.io.IOException, ServletException {
                HttpServletRequest http = (HttpServletRequest) request;
                if (WebUtils.getRequestUri(http).endsWith(PRIVATE)) seen.get(request.getDispatcherType()).incrementAndGet();
                if (request.getDispatcherType() == DispatcherType.ERROR) {
                    Object path = request.getAttribute("javax.servlet.error.request_uri");
                    Object status = request.getAttribute("javax.servlet.error.status_code");
                    if (path instanceof String && status instanceof Integer) initialErrors.put((String) path, (Integer) status);
                }
                chain.doFilter(request, response);
            }
        };
        FilterRegistrationBean<Filter> observerRegistration = new FilterRegistrationBean<>(observer);
        observerRegistration.setName("maintenance-dispatch-observer");
        observerRegistration.setOrder(0);
        observerRegistration.setDispatcherTypes(DispatcherType.REQUEST, DispatcherType.FORWARD, DispatcherType.INCLUDE, DispatcherType.ERROR);
        observerRegistration.addUrlPatterns("/*");
        context.getBeanFactory().registerSingleton("maintenanceObserverRegistration", observerRegistration);
        context.getBeanFactory().registerSingleton("maintenanceServletInitializer", initializer);
        context.getBeanFactory().registerSingleton("maintenanceErrorPageRegistrar", (ErrorPageRegistrar) registry -> registry.addErrorPages(new ErrorPage(HttpStatus.I_AM_A_TEAPOT, PRIVATE)));
    }
    private static Map<String, Object> http(int port, String contextPath, String path) throws Exception {
        System.out.println("SHIRO_MAINTENANCE_PROGRESS request: " + path);
        HttpURLConnection connection = (HttpURLConnection) new URL("http://127.0.0.1:" + port + contextPath + path).openConnection();
        connection.setConnectTimeout(5000); connection.setReadTimeout(5000); connection.setInstanceFollowRedirects(false);
        int status = connection.getResponseCode();
        InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        if (stream != null) try (InputStream input = stream) {
            byte[] bytes = new byte[4096]; int length;
            while ((length = input.read(bytes)) != -1) {
                if (body.size() + length > 4 * 1024 * 1024) throw new AssertionError("Bounded test response exceeded limit");
                body.write(bytes, 0, length);
            }
        }
        connection.disconnect();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", status);
        String text = new String(body.toByteArray(), StandardCharsets.UTF_8);
        result.put("privateMarker", text.contains("PRIVATE_TARGET_EXECUTED"));
        boolean denied = false;
        try { Map<?, ?> value = new ObjectMapper().readValue(text, Map.class); denied = Boolean.FALSE.equals(value.get("success")) && Integer.valueOf(401).equals(value.get("code")); }
        catch (java.io.IOException ignored) {}
        result.put("jwtDenied", denied);
        return result;
    }
    private static void actualDispatches(TomcatWebServer server, String contextPath) throws Exception {
        String[] modes = {"direct", "forward", "include", "error"};
        DispatcherType[] types = {DispatcherType.REQUEST, DispatcherType.FORWARD, DispatcherType.INCLUDE, DispatcherType.ERROR};
        for (int i = 0; i < modes.length; i++) {
            int before = seen.get(types[i]).get();
            Map<String, Object> result = http(server.getPort(), contextPath, i == 0 ? PRIVATE : ENTRY + "?mode=" + modes[i]);
            result.put("actualDispatcherObserved", seen.get(types[i]).get() > before);
            result.put("privateExecutionCount", privateExecutions.get());
            check("actual Tomcat " + types[i] + " denies private servlet without JWT", Boolean.TRUE.equals(result.get("actualDispatcherObserved"))
                    && privateExecutions.get() == 0 && !Boolean.TRUE.equals(result.get("privateMarker")) && Boolean.TRUE.equals(result.get("jwtDenied")));
            observations.add(item("actual dispatch result " + modes[i], result));
        }
        Map<String, Object> entry = http(server.getPort(), contextPath, ENTRY);
        check("synthetic public js entry is reachable without JWT", Integer.valueOf(200).equals(entry.get("status")) && privateExecutions.get() == 0);
        Map<String, Object> swagger = http(server.getPort(), contextPath, "/v2/api-docs");
        check("actual Swagger mapping retains configured anonymous access", Integer.valueOf(200).equals(swagger.get("status")));
        Map<String, Object> actuator = http(server.getPort(), contextPath, "/actuator/metrics");
        check("actual auxiliary Actuator route remains JWT protected", Integer.valueOf(401).equals(actuator.get("status")) && Boolean.TRUE.equals(actuator.get("jwtDenied")));
        for (String path : Arrays.asList("/v2/api-docs;synthetic", "/actuator/metrics;synthetic")) {
            Map<String, Object> denied = http(server.getPort(), contextPath, path);
            denied.put("initialErrorStatus", initialErrors.get(contextPath + path));
            check("actual global invalidRequest protects auxiliary mapping " + path, Integer.valueOf(400).equals(denied.get("initialErrorStatus"))
                    && !Boolean.TRUE.equals(denied.get("privateMarker")) && (Integer.valueOf(400).equals(denied.get("status")) || Integer.valueOf(401).equals(denied.get("status"))));
            observations.add(item("actual auxiliary invalid path " + path, denied));
        }
    }

    private static Map<String, Object> item(String name, Object value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("case", name); result.put("value", value); return result;
    }
    private static void check(String name, boolean passed) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("case", name); result.put("passed", passed); checks.add(result);
        System.out.println("SHIRO_MAINTENANCE_PROGRESS check: " + name + " = " + passed);
    }
    private static Set<Object> identities(Collection<?> values) {
        Set<Object> result = Collections.newSetFromMap(new IdentityHashMap<Object, Boolean>());
        result.addAll(values); return result;
    }
    private static List<String> filterNames(NamedFilterList chain) {
        List<String> names = new ArrayList<>();
        for (Filter value : chain) names.add(value.getClass().getName());
        return names;
    }
    private static HttpServletRequest request(final String rawPath, final String decodedPath, final DispatcherType dispatcher) {
        final Map<String, Object> attributes = new HashMap<>();
        if (dispatcher == DispatcherType.INCLUDE) {
            attributes.put("javax.servlet.include.request_uri", "/api" + rawPath);
            attributes.put("javax.servlet.include.context_path", "/api");
            attributes.put("javax.servlet.include.servlet_path", decodedPath);
        }
        return (HttpServletRequest) Proxy.newProxyInstance(VerifyShiroMaintenance.class.getClassLoader(), new Class<?>[]{HttpServletRequest.class}, (proxy, method, args) -> {
            switch (method.getName()) {
                case "getRequestURI": return "/api" + rawPath;
                case "getServletPath": return decodedPath;
                case "getContextPath": return "/api";
                case "getMethod": return "GET";
                case "getCharacterEncoding": return "UTF-8";
                case "getDispatcherType": return dispatcher;
                case "getAttribute": return attributes.get(args[0]);
                case "setAttribute": attributes.put((String) args[0], args[1]); return null;
                case "removeAttribute": attributes.remove(args[0]); return null;
                case "getAttributeNames": return Collections.enumeration(attributes.keySet());
                case "getParameterMap": return Collections.emptyMap();
                case "getParameterNames": case "getHeaderNames": return Collections.emptyEnumeration();
                case "getHeaders": return Collections.emptyEnumeration();
                case "toString": return "Synthetic servlet request";
                case "hashCode": return System.identityHashCode(proxy);
                case "equals": return proxy == args[0];
                default:
                    if (method.getReturnType() == boolean.class) return false;
                    if (method.getReturnType() == int.class) return 0;
                    if (method.getReturnType() == long.class) return 0L;
                    return null;
            }
        });
    }
    private static int invalidRequestStatus(InvalidRequestFilter filter, HttpServletRequest request) throws Exception {
        final int[] status = {200}; final boolean[] reached = {false};
        HttpServletResponse response = (HttpServletResponse) Proxy.newProxyInstance(VerifyShiroMaintenance.class.getClassLoader(), new Class<?>[]{HttpServletResponse.class}, (proxy, method, args) -> {
            if (method.getName().equals("sendError") || method.getName().equals("setStatus")) { status[0] = (Integer) args[0]; return null; }
            if (method.getName().equals("getStatus")) return status[0];
            if (method.getName().equals("getWriter")) return new PrintWriter(new StringWriter());
            if (method.getReturnType() == boolean.class) return false;
            if (method.getReturnType() == int.class) return 0;
            if (method.getReturnType() == long.class) return 0L;
            return null;
        });
        filter.doFilter(request, response, (req, res) -> reached[0] = true);
        return reached[0] ? 200 : status[0];
    }
    private static void inspect(ConfigurableApplicationContext context) throws Exception {
        ServletWebServerApplicationContext web = (ServletWebServerApplicationContext) context;
        Map<String, AbstractShiroFilter> filters = context.getBeansOfType(AbstractShiroFilter.class);
        check("one effective Shiro filter bean", identities(filters.values()).size() == 1);
        observations.add(item("Shiro filter bean names", new ArrayList<>(filters.keySet())));
        AbstractShiroFilter filter = context.getBean("shiroFilter", AbstractShiroFilter.class);
        DefaultWebSecurityManager manager = context.getBean("securityManager", DefaultWebSecurityManager.class);
        check("filter uses the manual securityManager", filter.getSecurityManager() == manager);
        BeanDefinition definition = web.getBeanFactory().getBeanDefinition("securityManager");
        check("manual securityManager originates from product ShiroConfig", "securityManager".equals(definition.getFactoryMethodName()) && definition.getFactoryBeanName() != null
                && context.getBean(definition.getFactoryBeanName()).getClass().getName().startsWith("org.jeecg.config.ShiroConfig"));
        check("manual realm remains the application ShiroRealm", manager.getRealms().size() == 1 && manager.getRealms().iterator().next() instanceof ShiroRealm);
        check("rememberMe manager is disabled", manager.getRememberMeManager() == null);
        DefaultSubjectDAO dao = (DefaultSubjectDAO) manager.getSubjectDAO();
        check("session storage remains disabled", dao.getSessionStorageEvaluator() instanceof DefaultSessionStorageEvaluator
                && !((DefaultSessionStorageEvaluator) dao.getSessionStorageEvaluator()).isSessionStorageEnabled());
        check("authorization advisor uses the manual manager", context.getBean(AuthorizationAttributeSourceAdvisor.class).getSecurityManager() == manager);

        Set<Object> registered = Collections.newSetFromMap(new IdentityHashMap<Object, Boolean>());
        boolean orderOne = true;
        for (FilterRegistrationBean<?> value : context.getBeansOfType(FilterRegistrationBean.class).values()) {
            if (value.isEnabled() && value.getFilter() instanceof AbstractShiroFilter) { registered.add(value.getFilter()); orderOne &= value.getOrder() == 1; }
        }
        check("one enabled explicit Shiro registration", registered.size() == 1 && registered.contains(filter));
        check("official Shiro registration keeps order 1", orderOne && !registered.isEmpty());
        TomcatWebServer server = (TomcatWebServer) web.getWebServer();
        StandardContext tomcat = null;
        for (Container value : server.getTomcat().getHost().findChildren()) if (value instanceof StandardContext) tomcat = (StandardContext) value;
        if (tomcat == null) throw new AssertionError("Actual servlet context absent");
        Set<String> shiroNames = new LinkedHashSet<>();
        for (org.apache.tomcat.util.descriptor.web.FilterDef value : tomcat.findFilterDefs()) if (value.getFilter() instanceof AbstractShiroFilter) shiroNames.add(value.getFilterName());
        check("Tomcat has one actual Shiro filter", shiroNames.size() == 1);
        Set<String> dispatchers = new TreeSet<>(); Set<String> patterns = new TreeSet<>();
        for (org.apache.tomcat.util.descriptor.web.FilterMap value : tomcat.findFilterMaps()) if (shiroNames.contains(value.getFilterName())) {
            dispatchers.addAll(Arrays.asList(value.getDispatcherNames())); patterns.addAll(Arrays.asList(value.getURLPatterns()));
        }
        check("actual mapping covers REQUEST FORWARD INCLUDE ERROR", dispatchers.equals(new TreeSet<>(Arrays.asList("REQUEST", "FORWARD", "INCLUDE", "ERROR"))));
        check("actual Shiro mapping covers all paths", patterns.contains("/*"));
        observations.add(item("actual Shiro dispatcher mappings", dispatchers));
        for (String name : shiroNames) {
            FilterRegistration registration = web.getServletContext().getFilterRegistration(name);
            check("ServletContext confirms Shiro registration " + name, registration != null && registration.getUrlPatternMappings().contains("/*"));
        }

        ShiroFilterFactoryBean factory = context.getBean("&shiroFilter", ShiroFilterFactoryBean.class);
        check("factory and registration use the same filter instance", factory.getObject() == filter);
        check("old and official names alias the same factory and product", context.getBean("&shiroFilterFactoryBean") == factory && context.getBean("shiroFilterFactoryBean") == filter);
        check("nested dispatcher filtering remains enabled", !factory.getShiroFilterConfiguration().isFilterOncePerRequest());
        Map<String, String> rules = factory.getFilterChainDefinitionMap();
        List<String> paths = new ArrayList<>(rules.keySet());
        check("media rule precedes generic extension and final JWT rules", paths.indexOf("/sys/common/static/**") == 0
                && paths.indexOf("/**/*.js") > 0 && paths.indexOf("/**") == paths.size() - 1
                && "mediaJwt".equals(rules.get("/sys/common/static/**")) && "jwt".equals(rules.get("/**")));
        FilterChainManager chains = ((PathMatchingFilterChainResolver) filter.getFilterChainResolver()).getFilterChainManager();
        boolean globals = true;
        for (String name : chains.getChainNames()) { NamedFilterList chain = chains.getChain(name); if (chain.isEmpty() || !(chain.get(0) instanceof InvalidRequestFilter)) globals = false; }
        check("every resolved chain starts with actual invalidRequest filter", globals && !chains.getChainNames().isEmpty());
        String[] keys = {"/sys/common/static/**", "/teaching/teachingWork/studentWorkInfo", "/**"};
        Class<?>[] kinds = {MediaJwtFilter.class, OptionalJwtFilter.class, JwtFilter.class};
        for (int i = 0; i < keys.length; i++) {
            NamedFilterList chain = chains.getChain(keys[i]);
            check("resolved JWT rule " + keys[i], chain != null && chain.size() == 2 && chain.get(0) instanceof InvalidRequestFilter && chain.get(1).getClass() == kinds[i]);
            if (chain != null) observations.add(item("resolved filters " + keys[i], filterNames(chain)));
        }
        InvalidRequestFilter invalid = (InvalidRequestFilter) chains.getFilters().get("invalidRequest");
        check("invalidRequest guards remain enabled", invalid.isBlockSemicolon() && invalid.isBlockBackslash() && invalid.isBlockTraversal()
                && invalid.isBlockEncodedPeriod() && invalid.isBlockEncodedForwardSlash() && invalid.isBlockRewriteTraversal() && invalid.isBlockNonAscii());
        for (DispatcherType type : new DispatcherType[]{DispatcherType.REQUEST, DispatcherType.FORWARD, DispatcherType.INCLUDE, DispatcherType.ERROR}) {
            check(type + " finite synthetic traversal denied", invalidRequestStatus(invalid, request("/sys/common/static/../private.txt", "/sys/common/static/../private.txt", type)) == 400);
        }
        for (String path : Arrays.asList("/sys/common/static/a;v.txt", "/sys/common/static/a%3bv.txt", "/sys/common/static/a%5cb.txt", "/sys/common/static/%2e%2e/private.txt", "/sys/common/static/a%2fb.txt")) {
            check("invalid path remains denied " + path, invalidRequestStatus(invalid, request(path, path, DispatcherType.REQUEST)) == 400);
        }
        for (String path : Arrays.asList("/sys/common/static/space name.txt", "/sys/common/static/plus+name.txt", "/sys/common/static/50%name.txt")) {
            check("finite printable filename passes invalidRequest " + path, invalidRequestStatus(invalid, request(path.replace(" ", "%20"), path, DispatcherType.REQUEST)) == 200);
        }
        int unicode = invalidRequestStatus(invalid, request("/sys/common/static/%E8%AF%BE%E7%A8%8B.txt", "/sys/common/static/课程.txt", DispatcherType.REQUEST));
        observations.add(item("Unicode decoded filename existing restriction (not support acceptance)", unicode));

        Map<String, RequestMappingHandlerMapping> mappings = context.getBeansOfType(RequestMappingHandlerMapping.class);
        Map<String, String> helperClasses = new LinkedHashMap<>();
        for (Map.Entry<String, RequestMappingHandlerMapping> value : mappings.entrySet()) {
            helperClasses.put(value.getKey(), value.getValue().getUrlPathHelper().getClass().getName());
            Map<String, Object> details = new LinkedHashMap<>();
            details.put("mappingClass", value.getValue().getClass().getName());
            details.put("helperClass", value.getValue().getUrlPathHelper().getClass().getName());
            details.put("superclassRegistryCount", value.getValue().getHandlerMethods().size());
            if ("springfox.documentation.spring.web.PropertySourcedRequestMappingHandlerMapping".equals(value.getValue().getClass().getName())) {
                // Springfox routes through its private registry instead of the
                // superclass registry exposed by getHandlerMethods(). Read it
                // only in this test launcher; do not infer absence from 0.
                java.lang.reflect.Field registry = value.getValue().getClass().getDeclaredField("handlerMethods");
                registry.setAccessible(true);
                Map<?, ?> active = (Map<?, ?>) registry.get(value.getValue());
                List<Map<String, Object>> handlers = new ArrayList<>();
                for (Map.Entry<?, ?> entry : active.entrySet()) {
                    Map<String, Object> handler = new LinkedHashMap<>();
                    handler.put("path", entry.getKey());
                    handler.put("handlerType", ((HandlerMethod) entry.getValue()).getBeanType().getName());
                    handlers.add(handler);
                }
                details.put("activeCustomRegistryCount", active.size());
                details.put("activeCustomHandlers", handlers);
            }
            if (!"requestMappingHandlerMapping".equals(value.getKey())) {
                List<Map<String, Object>> handlers = new ArrayList<>();
                value.getValue().getHandlerMethods().forEach((info, method) -> {
                    Map<String, Object> handler = new LinkedHashMap<>();
                    handler.put("patterns", info.getPatternsCondition().getPatterns());
                    handler.put("handlerType", method.getBeanType().getName());
                    handlers.add(handler);
                });
                details.put("handlers", handlers);
            }
            observations.add(item("mapping scope " + value.getKey(), details));
        }
        observations.add(item("actual MVC mapping helper classes", helperClasses));
        RequestMappingHandlerMapping mapping = context.getBean("requestMappingHandlerMapping", RequestMappingHandlerMapping.class);
        check("official adapter targets actual business requestMappingHandlerMapping", mapping.getUrlPathHelper() instanceof ShiroUrlPathHelper);
        for (DispatcherType type : new DispatcherType[]{DispatcherType.REQUEST, DispatcherType.FORWARD, DispatcherType.INCLUDE, DispatcherType.ERROR}) {
            HttpServletRequest request = request("/teaching/teachingCourse/getHomeCourse", "/teaching/teachingCourse/getHomeCourse", type);
            check(type + " MVC and Shiro resolve the same finite path", mapping.getUrlPathHelper().getPathWithinApplication(request).equals(WebUtils.getPathWithinApplication(request)));
        }
        check("servlet is bound to a random loopback test port", "127.0.0.1".equals(context.getEnvironment().getProperty("server.address"))
                && "0".equals(context.getEnvironment().getProperty("server.port")) && server.getPort() > 0);
        actualDispatches(server, web.getServletContext().getContextPath());
    }
    public static void main(String[] args) throws Exception {
        ConfigurableApplicationContext context = null;
        try {
            SpringApplication app = new SpringApplication(JeecgApplication.class);
            app.addInitializers(VerifyShiroMaintenance::installTestServlets);
            System.out.println("SHIRO_MAINTENANCE_PROGRESS starting test context");
            context = app.run(args);
            System.out.println("SHIRO_MAINTENANCE_PROGRESS test context started");
            inspect(context);
        } catch (Throwable failure) {
            check("test application context and probe completed", false);
            List<String> classes = new ArrayList<>();
            for (Throwable cause = failure; cause != null && classes.size() < 12; cause = cause.getCause()) classes.add(cause.getClass().getName());
            observations.add(item("failure exception classes (messages withheld)", classes));
        } finally {
            if (context != null) {
                System.out.println("SHIRO_MAINTENANCE_PROGRESS closing test context");
                context.close();
                System.out.println("SHIRO_MAINTENANCE_PROGRESS test context closed");
            }
        }
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("scope", "exact JAR classes and real localtest context; Tomcat registration and actual loopback REQUEST/FORWARD/INCLUDE/ERROR test-only servlet dispatch; supplemental proxy request checks labelled synthetic; no login");
        report.put("checks", checks); report.put("observations", observations);
        System.out.println("SHIRO_MAINTENANCE_JSON " + new ObjectMapper().writeValueAsString(report));
        int status = 0;
        for (Map<String, Object> value : checks) if (!Boolean.TRUE.equals(value.get("passed"))) status = 1;
        // Legacy application infrastructure can leave non-daemon threads after
        // context.close(); their source was not identified. This launcher exits;
        // context.close() and report generation above must complete first.
        System.exit(status);
    }
}
