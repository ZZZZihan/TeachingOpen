import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.qiniu.util.Auth;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.jeecg.modules.common.util.QiniuUploadPolicy;
import org.apache.shiro.authz.UnauthorizedException;

/** Offline policy verification against the exact packaged SDK; never contacts cloud storage. */
public final class VerifyQiniuOwnership {
    static JsonObject policy(String token) {
        String encoded = token.split(":")[2];
        return new JsonParser().parse(new String(Base64.getUrlDecoder().decode(encoded), StandardCharsets.UTF_8)).getAsJsonObject();
    }
    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println("PASS " + name);
    }
    public static void main(String[] args) {
        Auth auth = Auth.create("synthetic-access", "synthetic-secret");
        String a = QiniuUploadPolicy.prefix("fixture_student_a");
        String b = QiniuUploadPolicy.prefix("fixture_student_b");
        check("different users have distinct object prefixes", !a.equals(b) && a.endsWith("/"));
        JsonObject generic = policy(QiniuUploadPolicy.token(auth, "synthetic-bucket", "fixture_student_a", null, 3600));
        check("generic token is confined to current user and insert-only", generic.get("scope").getAsString().equals("synthetic-bucket:" + a)
                && generic.get("isPrefixalScope").getAsInt() == 1 && generic.get("insertOnly").getAsInt() == 1);
        JsonObject exact = policy(QiniuUploadPolicy.token(auth, "synthetic-bucket", "fixture_student_a", a + "project.py", 3600));
        check("exact-key token still forbids overwrite", exact.get("scope").getAsString().equals("synthetic-bucket:" + a + "project.py") && exact.get("insertOnly").getAsInt() == 1);
        for (String key : new String[] {b+"project.py", "legacy/project.py", a, a+"../escape", a+"./escape", a+"dir//file", a+"dir\\file", a+"dir:file", a+"dir\nfile", a+"dir\n\nfile"}) {
            boolean denied = false;
            try { QiniuUploadPolicy.token(auth, "synthetic-bucket", "fixture_student_a", key, 3600); }
            catch (UnauthorizedException expected) { denied = true; }
            check("foreign or malformed key rejected " + (++sequence), denied);
        }
        long remaining = generic.get("deadline").getAsLong() - System.currentTimeMillis()/1000;
        check("upload policy is time bounded", remaining >= 3595 && remaining <= 3600);
    }
    static int sequence;
}
