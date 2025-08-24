<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>CHOKED</title>
 
<script language="javascript" type="text/javascript" src="script.js"></script>
<script>
document.addEventListener("DOMContentLoaded", function() {
  setInterval(function() {
    window.location.reload();
  }, 100000); // refresh every 100 seconds
});
</script>

</head>
<?php
// p1.php - ZKT-only version (uses mysql_* compatibility wrappers for MySQL)
error_reporting(E_ALL);
ini_set('display_errors', 1);

include("database1.php"); // provides $mylink (PDO-based compatibility shim)

// Path to ZKT Access DB - change if needed
$dbName_zk = "D:/ABEDY/attendance-system/backend/att2000.mdb";

if (!file_exists($dbName_zk)) {
    die("Could not find ZKT DB file: $dbName_zk");
}

/**
 * LOCKING: directory-based lock to coordinate with Python scheduler.
 * Uses atomic mkdir for acquisition; removes stale lock directories older than $stale_seconds.
 */
function acquire_lock_dir($lock_dir, $timeout = 15, $stale_seconds = 60) {
    $start = time();
    while (true) {
        // attempt to create lock dir (atomic on Windows & Linux)
        $ok = @mkdir($lock_dir);
        if ($ok) {
            // wrote a stamp file for debugging
            $stamp = $lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt";
            $pid = getmypid();
            @file_put_contents($stamp, "pid={$pid}\ncreated=" . date('c') . "\n");
            return true;
        }

        // if lock exists, consider stale
        if (file_exists($lock_dir)) {
            $mtime = @filemtime($lock_dir);
            if ($mtime !== false && (time() - $mtime) > $stale_seconds) {
                // stale: attempt to remove lock dir (best effort)
                @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
                @rmdir($lock_dir);
                // small pause then retry immediately
                usleep(50000);
                continue;
            }
        }

        // timeout check
        if ((time() - $start) >= $timeout) {
            return false;
        }
        // short sleep before retrying
        usleep(200000); // 200ms
    }
}

function release_lock_dir($lock_dir) {
    // remove stamp and the dir (best-effort)
    @unlink($lock_dir . DIRECTORY_SEPARATOR . "lockinfo.txt");
    @rmdir($lock_dir);
}

/**
 * Decide lock dir location: place it next to the Access DB file so both processes can access it.
 * e.g. if the MDB is D:/.../att2000.mdb, lock dir will be D:/.../access_lock
 */
$lock_dir = dirname($dbName_zk) . DIRECTORY_SEPARATOR . "access_lock";
$lock_timeout = 15;    // seconds to wait to acquire the lock
$lock_stale = 60;      // consider the lock stale after 60s and allow removal

$got_lock = acquire_lock_dir($lock_dir, $lock_timeout, $lock_stale);
if (!$got_lock) {
    // cannot acquire the lock in time: skip this run to avoid conflicts
    echo "Could not acquire Access DB lock (busy). Skipping this run.<br>";
    // Optionally: exit silently or return HTTP 503; keeping behavior minimal:
    exit;
}

try {
    try {
        // DSN that supports .mdb and .accdb
        $dsn2 = "odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=$dbName_zk;";
        $db_zk = new PDO($dsn2);
        $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    } catch (PDOException $e) {
        // release lock before aborting
        release_lock_dir($lock_dir);
        die("Access DB connection failed: " . $e->getMessage());
    }

    // lookback date (same logic you used)
    $lDate = date('Y-m-d', strtotime("-10 day", strtotime(date("Y-m-d"))));

    // --- ZKT devices only ---
    $slZK = 0;
    $sqlZK = "SELECT *
			FROM CHECKINOUT t1
			INNER JOIN USERINFO t2 ON t2.USERID = t1.USERID
			WHERE Format(CHECKTIME,'YYYY-MM-DD') > :lDate
			ORDER BY CHECKTIME;
			";
    $stmt2 = $db_zk->prepare($sqlZK);
    $stmt2->execute([':lDate' => $lDate]);

    while ($row = $stmt2->fetch(PDO::FETCH_ASSOC)) {
        $logDate = date("Y-m-d", strtotime($row["CHECKTIME"]));
        $logTime = date("H:i:s", strtotime("-10 minutes", strtotime($row['CHECKTIME'])));
        $userId  = isset($row['Badgenumber']) ? $row['Badgenumber'] : '';

        // keep your original behavior: skip if badge length > 4
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

        // escape using mysql_real_escape_string (compat shim in database1.php)
        $u_logDate    = mysql_real_escape_string($logDate, $mylink);
        $u_userId     = mysql_real_escape_string($userId, $mylink);
        $u_logTime    = mysql_real_escape_string($logTime, $mylink);
        $u_accessDoor = mysql_real_escape_string($accessDoor, $mylink);
        $u_accessDev  = mysql_real_escape_string($accessDevice, $mylink);

        $ins_sql = "INSERT INTO att_raw_data VALUES(NULL, '$u_logDate', '$u_userId', '$u_userId', '', '$u_logTime', '0', '$u_accessDoor', '', '$u_accessDev')";

        echo "SQL: " . $ins_sql . "\n";
        $res = @mysql_query($ins, $mylink);

        // compatibility shim's mysql_query() returns number of affected rows (int) or FALSE on error
        if ($res === false) {
            $err = mysql_error(); // shim provides this
            if (!empty($err)) {
                echo "MySQL insert error (ZKT) for user '$userId': $err<br>";
            }
        } else {
            // $res is number of affected rows. INSERT IGNORE returns 1 for new row, 0 for duplicates.
            if (is_numeric($res) && intval($res) > 0) {
                $slZK++;
            }
        }
    }

    echo "Fetched $slZK Record(s) from ZKT Devices<br>";

    // close connection (optional for compatibility shim)
    @mysql_close($mylink);

    // close PDO connection to Access
    $db_zk = null;

} finally {
    // always release lock
    release_lock_dir($lock_dir);
}
?>
