package org.jeecg.modules.message.websocket;

import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.SpringContextUtils;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.service.ITeachingWorkService;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.springframework.stereotype.Component;
import javax.websocket.CloseReason;
import javax.websocket.OnClose;
import javax.websocket.OnError;
import javax.websocket.OnMessage;
import javax.websocket.OnOpen;
import javax.websocket.Session;
import javax.websocket.server.ServerEndpoint;
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CopyOnWriteArraySet;

/** Scratch newline JSON, bound to one readable work and verified identity. */
@Component
@ServerEndpoint("/websocket/scratch/cloudData")
public class ScratchWebSocket {
    private static final CopyOnWriteArraySet<ScratchWebSocket> subscribers = new CopyOnWriteArraySet<>();
    private Session session;
    private volatile String projectId;
    private String token;
    private String userId;
    private boolean closed;
    private final ArrayDeque<String> outbound = new ArrayDeque<>();
    private int queuedCharacters;

    @OnOpen
    public void onOpen(Session session) {
        this.session = session;
        session.setMaxTextMessageBufferSize(16384);
        session.setMaxIdleTimeout(10000);
        session.getAsyncRemote().setSendTimeout(5000);
    }

    @OnMessage
    public void onMessage(String message) {
        String update = null;
        String project = null;
        synchronized (this) {
            if (closed) return;
            try {
                JSONObject request = JSONObject.parseObject(message);
                if (request == null) throw new IllegalArgumentException();
                String method = text(request, "method");
                String requestedProject = text(request, "project_id");
                String credential = text(request, "token");
                if (credential != null && credential.isEmpty()) credential = null;
                if (requestedProject == null || !requestedProject.matches("[A-Za-z0-9_-]{1,64}")
                        || "create".equals(requestedProject) || (credential != null && credential.length() > 4096)) {
                    reject(CloseReason.CloseCodes.VIOLATED_POLICY); return;
                }
                if (projectId == null) {
                    if (!"handshake".equals(method)) throw new IllegalArgumentException();
                    token = credential;
                    LoginUser user = authenticatedUser();
                    userId = user == null ? null : user.getId();
                    projectId = requestedProject;
                } else if (!projectId.equals(requestedProject) || !Objects.equals(token, credential)) {
                    reject(CloseReason.CloseCodes.VIOLATED_POLICY); return;
                }
                LoginUser user = authenticatedUser();
                TeachingWork work = readableWork(user);
                if (work == null) { reject(CloseReason.CloseCodes.VIOLATED_POLICY); return; }
                project = projectId;
                if ("handshake".equals(method)) {
                    // Register under the connection monitor before reading so a concurrent
                    // update waits for this snapshot rather than missing this subscriber.
                    subscribers.add(this);
                    Map<Object, Object> snapshot = store().snapshot(projectId);
                    // Validate legacy state before sending; never silently truncate it.
                    for (Map.Entry<Object, Object> entry : snapshot.entrySet()) {
                        validateName((String) entry.getKey()); validateValue(entry.getValue());
                    }
                    session.setMaxIdleTimeout(90000);
                    for (Map.Entry<Object, Object> entry : snapshot.entrySet()) {
                        send(variable(projectId, (String) entry.getKey(), String.valueOf(entry.getValue())));
                    }
                    ack(null, "OK");
                } else {
                    if (!subscribers.contains(this)) throw new IllegalArgumentException();
                    String name = text(request, "name"); validateName(name);
                    boolean owner = user != null && user.getId().equals(work.getUserId());
                    if (user == null || (!owner && !"set".equals(method))) { ack(name, "FAIL"); return; }
                    String value = null, newName = null;
                    if ("set".equals(method) || "create".equals(method)) value = validateValue(request.get("value"));
                    else if ("rename".equals(method)) { newName = text(request, "new_name"); validateName(newName); }
                    else if (!"delete".equals(method)) throw new IllegalArgumentException();
                    long result = store().mutate(projectId, method, name, value, newName, owner);
                    ack(name, result == 0 ? "FAIL" : "OK");
                    if (result == 1 && ("set".equals(method) || "create".equals(method))) update = variable(projectId, name, value);
                }
            } catch (org.apache.shiro.authc.AuthenticationException | IllegalArgumentException failure) {
                reject(CloseReason.CloseCodes.VIOLATED_POLICY);
            } catch (RuntimeException failure) {
                // No raw frames, credentials, values or stack traces in logs.
                reject(CloseReason.CloseCodes.UNEXPECTED_CONDITION);
            }
        }
        // Do not acquire another connection's monitor while holding this one.
        if (update != null) for (ScratchWebSocket subscriber : subscribers) subscriber.deliver(project, update);
    }

    private LoginUser authenticatedUser() {
        if (token == null) return null;
        LoginUser user = SpringContextUtils.getBean(ShiroRealm.class).checkUserTokenIsEffect(token);
        if (user == null || (userId != null && !userId.equals(user.getId()))) throw new IllegalArgumentException();
        return user;
    }

    private TeachingWork readableWork(LoginUser user) {
        TeachingWork work = SpringContextUtils.getBean(ITeachingWorkService.class).getById(projectId);
        if (work == null || !("1".equals(work.getWorkType()) || "2".equals(work.getWorkType()))) return null;
        return SpringContextUtils.getBean(TeachingAccessService.class).canReadCommunityWork(work, user) ? work : null;
    }

    private ScratchCloudStore store() { return SpringContextUtils.getBean(ScratchCloudStore.class); }

    private synchronized void deliver(String project, String update) {
        if (closed || !Objects.equals(projectId, project)) return;
        try {
            if (readableWork(authenticatedUser()) == null) { reject(CloseReason.CloseCodes.VIOLATED_POLICY); return; }
            send(update);
        } catch (RuntimeException failure) { reject(CloseReason.CloseCodes.VIOLATED_POLICY); }
    }

    private synchronized void send(String message) {
        if (closed || !session.isOpen()) { onClose(); return; }
        if (outbound.size() >= 128 || queuedCharacters + message.length() > 524288) {
            reject(CloseReason.CloseCodes.UNEXPECTED_CONDITION); return;
        }
        outbound.addLast(message);
        queuedCharacters += message.length();
        if (outbound.size() == 1) sendNext();
    }

    private void sendNext() {
        try {
            session.getAsyncRemote().sendText(outbound.peekFirst(), result -> {
                synchronized (ScratchWebSocket.this) {
                    if (closed) return;
                    if (!result.isOK()) { reject(CloseReason.CloseCodes.UNEXPECTED_CONDITION); return; }
                    queuedCharacters -= outbound.removeFirst().length();
                    if (!outbound.isEmpty()) sendNext();
                }
            });
        } catch (RuntimeException failure) { reject(CloseReason.CloseCodes.UNEXPECTED_CONDITION); }
    }

    private void ack(String name, String reply) {
        JSONObject message = new JSONObject();
        message.put("method", "ack"); message.put("name", name); message.put("reply", reply);
        send(message.toJSONString() + "\n");
    }

    private static String variable(String project, String name, String value) {
        JSONObject message = new JSONObject();
        message.put("method", "set"); message.put("project_id", project); message.put("name", name); message.put("value", value);
        return message.toJSONString() + "\n";
    }

    private static String text(JSONObject request, String key) {
        Object value = request.get(key);
        if (value != null && !(value instanceof String)) throw new IllegalArgumentException();
        return (String) value;
    }

    private static void validateName(String name) {
        if (name == null || name.trim().isEmpty() || name.length() > 128 || name.indexOf('\0') >= 0) throw new IllegalArgumentException();
    }

    private static String validateValue(Object value) {
        if (!(value instanceof String) && !(value instanceof Number)) throw new IllegalArgumentException();
        String result = String.valueOf(value);
        if (result.length() > 1024) throw new IllegalArgumentException();
        return result;
    }

    private synchronized void reject(CloseReason.CloseCode code) {
        onClose();
        if (session != null && session.isOpen()) {
            try { session.close(new CloseReason(code, "Cloud session unavailable")); }
            catch (IOException ignored) { /* Already disconnected. */ }
        }
    }

    @OnClose
    public synchronized void onClose() {
        closed = true; subscribers.remove(this); token = null; userId = null;
        outbound.clear(); queuedCharacters = 0;
    }

    @OnError
    public void onError(Throwable failure) { reject(CloseReason.CloseCodes.UNEXPECTED_CONDITION); }
}
