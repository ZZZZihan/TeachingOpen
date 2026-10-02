import java.io.BufferedReader;
import java.io.InputStreamReader;
import org.jeecg.common.util.PasswordUtil;

/** Local fixture helper. Credentials arrive through stdin, never command arguments. */
public class FixturePassword {
    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, "UTF-8"));
        String username = in.readLine();
        String password = in.readLine();
        String salt = in.readLine();
        System.out.print(PasswordUtil.encrypt(username, password, salt));
    }
}
