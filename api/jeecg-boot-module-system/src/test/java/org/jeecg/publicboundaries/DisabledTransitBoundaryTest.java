package org.jeecg.publicboundaries;

import com.sun.net.httpserver.HttpServer;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.system.controller.CommonController;
import org.junit.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.net.InetSocketAddress;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.Assert.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import org.springframework.http.HttpMethod;

public class DisabledTransitBoundaryTest {
    @Test public void everyRequestMethodIsDeniedWithoutAnyOutboundRequestOrRequestInspection() throws Exception {
        AtomicInteger outbound = new AtomicInteger();
        HttpServer sink = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        sink.createContext("/", exchange -> {
            outbound.incrementAndGet();
            exchange.sendResponseHeaders(200, 0);
            exchange.getResponseBody().close();
        });
        sink.start();
        try {
            CommonController controller = new CommonController();
            MockMvc http = MockMvcBuilders.standaloneSetup(controller).build();
            String destination = "http://127.0.0.1:" + sink.getAddress().getPort() + "/probe";
            // Null request proves the retired method no longer reads a caller's token or body.
            Result result = controller.transitRESTful(destination, null);
            assertFalse(result.isSuccess()); assertEquals(Integer.valueOf(403), result.getCode());
            for (HttpMethod method : new HttpMethod[]{HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.DELETE, HttpMethod.PATCH}) {
                http.perform(request(method, "/sys/common/transitRESTful").param("url", destination)
                        .header("X-Access-Token", "synthetic-secret").content("{\"probe\":true}"))
                        .andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(403));
            }
            assertEquals(0, outbound.get());
        } finally {
            sink.stop(0);
        }
    }
}
