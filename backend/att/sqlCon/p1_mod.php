<?php
// p1_dummy.php - Diagnostic version: reads Access CHECKINOUT and shows exact rows+SQL
// DOES NOT include database1.php to avoid attempting production DB connection.
//
// Edit the DUMMY_MYSQL_* constants below to match a test DB you control.
// You can run this on the same server where att2000.mdb lives.

error_reporting(E_ALL);
ini_set('display_errors', 1);

// ------------------------------
// Dummy MySQL destination (edit these)
define('DUMMY_MYSQL_HOST','127.0.0.1');
define('DUMMY_MYSQL_USER','dummy_user');
define('DUMMY_MYSQL_PASS','dummy_pass');
define('DUMMY_MYSQL_DB','dummy_db');
define('DUMMY_MYSQL_PORT', 3306);

// Try to connect to dummy DB (mysqli)
$dummy_conn = @mysqli_connect(DUMMY_MYSQL_HOST, DUMMY_MYSQL_USER, DUMMY_MYSQL_PASS, DUMMY_MYSQL_DB, DUMMY_MYSQL_PORT);
if (!$dummy_conn) {
    $dummy_err = mysqli_connect_error();
    $dummy_connected = false;
} else {
    $dummy_connected = true;
    // set charset for safety
    mysqli_set_charset($dummy_conn, 'utf8mb4');
}

// Path to ZKT Access DB - change if needed
$dbName_zk = "E:/ShareME/SBAC TAO/NewYear25/attendance-system/backend/att2000.mdb";

// Quick check
if (!file_exists($dbName_zk)) {
    die("Could not find ZKT DB file: $dbName_zk");
}

/**
 * LOCKING: directory-based lock to coordinate with other processes.
 * Uses atomic mkdir for acquisition; stale-lock removal supported.
 */
function acquire_lock_dir($lock_dir, $timeout = 15, $stale_seconds = 60) {
    $start = time();
    while (true) {
        $ok = @mkdir($lock_dir);
        if ($ok) {
            $stamp = $lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt";
            $pid = getmypid();
            @file_put_contents($stamp, "pid={$pid}\ncreated=" . date('c') . "\n");
            return true;
        }
        if (file_exists($lock_dir)) {
            $mtime = @filemtime($lock_dir);
            if ($mtime !== false && (time() - $mtime) > $stale_seconds) {
                @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
                @rmdir($lock_dir);
                usleep(50000);
                continue;
            }
        }
        if ((time() - $start) >= $timeout) {
            return false;
        }
        usleep(200000); // 200ms
    }
}
function release_lock_dir($lock_dir) {
    @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
    @rmdir($lock_dir);
}

// Decide lock dir next to MDB
$lock_dir = dirname($dbName_zk) . DIRECTORY_SEPARATOR . "access_lock";
$lock_timeout = 15;
$lock_stale = 60;

$got_lock = acquire_lock_dir($lock_dir, $lock_timeout, $lock_stale);
if (!$got_lock) {
    echo "Could not acquire Access DB lock (busy). Skipping this run.<br>";
    exit;
}

try {
    // Open Access DB via ODBC PDO
    try {
        $dsn2 = "odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=$dbName_zk;";
        $db_zk = new PDO($dsn2);
        $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    } catch (PDOException $e) {
        release_lock_dir($lock_dir);
        die("Access DB connection failed: " . $e->getMessage());
    }

    // lookback window
    $lDate = date('Y-m-d', strtotime("-10 day", strtotime(date("Y-m-d"))));

    // Query CHECKINOUT joining USERINFO (like your original)
    $sqlZK = "SELECT *
			FROM CHECKINOUT t1
			INNER JOIN USERINFO t2 ON t2.USERID = t1.USERID
			WHERE Format(CHECKTIME,'YYYY-MM-DD') > :lDate
			ORDER BY CHECKTIME;
			";
    $stmt2 = $db_zk->prepare($sqlZK);
    $stmt2->execute([':lDate' => $lDate]);

    // Output header
    echo "<h2>ZK -> Diagnostic (will show what would be sent)</h2>\n";
    if (!$dummy_connected) {
        echo "<div style='color:darkred; font-weight:bold;'>Dummy MySQL not connected: " . htmlspecialchars($dummy_err ?? 'unknown') . ". Inserts will be skipped but rows are displayed.</div>\n";
    } else {
        echo "<div style='color:green;'>Dummy MySQL connected. Rows will be attempted against dummy DB.</div>\n";
    }

    echo "<pre style='white-space:pre-wrap; word-break:break-word;'>\n";
    $counter = 0;

    while ($row = $stmt2->fetch(PDO::FETCH_ASSOC)) {
        $raw_checktime = $row["CHECKTIME"] ?? null;
        // Normalize date/time exactly as your script does:
        $logDate = date("Y-m-d", strtotime($raw_checktime));
        $logTime = date("H:i:s", strtotime("-10 minutes", strtotime($raw_checktime)));
        $userId  = isset($row['Badgenumber']) ? $row['Badgenumber'] : '';

        // Keep original behavior: skip if badge length > 4
        if (strlen($userId) > 4) continue;

        $accessDevice = 'FLASK-ZKT-' . (isset($row['sn']) ? $row['sn'] : '');
        $accessDoor   = isset($row['sn']) ? $row['sn'] : '';

        // Build payload that would be inserted into att_raw_data
        $payload = [
            'date' => $logDate,
            'time' => $logTime,
            'badge' => $userId,
            'door' => $accessDoor,
            'device' => $accessDevice,
            // mark origin so admin can identify these rows if you re-enable prod insert
            'source' => 'flask_php_zk_script'
        ];

        // Show JSON for clarity
        echo "ROW: " . json_encode($payload, JSON_UNESCAPED_SLASHES) . "\n";

        // Build SQL exactly as original (use NULL for first column)
        // Escape values for SQL using mysqli if available, else addslashes fallback.
        if (!function_exists('safe_escape_local')) {
			function safe_escape_local($value) {
				if ($value === null) return "NULL";
				return "'" . addslashes($value) . "'";
			}
		}
        $u_logDate    = safe_escape_local($logDate);
        $u_userId     = safe_escape_local($userId);
        $u_logTime    = safe_escape_local($logTime);
        $u_accessDoor = safe_escape_local($accessDoor);
        $u_accessDev  = safe_escape_local($accessDevice);

        $ins_sql = "INSERT INTO att_raw_data VALUES(NULL, '$u_logDate', '$u_userId', '$u_userId', '', '$u_logTime', '0', '$u_accessDoor', '', '$u_accessDev')";

        echo "SQL: " . $ins_sql . "\n";

        // Attempt dummy insert (no IGNORE so errors surface)
        if ($dummy_connected) {
            $res = @mysqli_query($dummy_conn, $ins_sql);
            if ($res === false) {
                $err = mysqli_error($dummy_conn);
                echo "DUMMY INSERT FAILED: " . htmlspecialchars($err) . "\n";
            } else {
                echo "DUMMY INSERT OK\n";
            }
        } else {
            echo "DUMMY DB not connected - skipping insert\n";
        }

        echo "----\n";
        $counter++;
    }

    echo "Fetched $counter rows shown (ZKT)\n";
    echo "</pre>\n";

    // Cleanup
    $db_zk = null;

} finally {
    // release lock and close dummy connection
    release_lock_dir($lock_dir);
    if (isset($dummy_conn) && $dummy_conn) {
        mysqli_close($dummy_conn);
    }
}
?>
