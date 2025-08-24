<?php
// database1.php  -- compatibility layer for environments WITHOUT old mysql_*
// It creates $mylink (PDO) and defines mysql_* wrappers so existing code works.

error_reporting(E_ALL);
ini_set('display_errors', 1);

$mysql_host = "10.9.1.1";
$mysql_user = "zkt";
$mysql_pass = "abc123X";
$mysql_db   = "hr_db";

try {
    // create PDO connection and store in $mylink so your code sees the same name
    $mylink = new PDO(
        "mysql:host={$mysql_host};dbname={$mysql_db};charset=utf8",
        $mysql_user,
        $mysql_pass,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
} catch (PDOException $e) {
    // die with clear message so you can see exact error
    die("<h3>Could not connect database: " . $e->getMessage() . "</h3>\n");
}

// If the old mysql_real_escape_string (and other mysql_*) functions are missing,
// create thin wrappers that map to PDO behavior so your legacy code keeps working.
if (!function_exists('mysql_real_escape_string')) {
    function mysql_real_escape_string($str, $link = null) {
        if (is_null($str)) return '';
        $pdo = $link ? $link : $GLOBALS['mylink'];
        // PDO::quote returns the value with surrounding quotes, remove them
        $quoted = $pdo->quote($str);
        if ($quoted === false) {
            // fallback
            return addslashes((string)$str);
        }
        return substr($quoted, 1, -1);
    }

    function mysql_query($sql, $link = null) {
        $pdo = $link ? $link : $GLOBALS['mylink'];
        try {
            // exec() returns number of affected rows or false on failure
            $res = $pdo->exec($sql);
            if ($res === false) {
                return false;
            }
            return $res;
        } catch (PDOException $e) {
            $GLOBALS['_mysql_error'] = $e->getMessage();
            return false;
        }
    }

    function mysql_error() {
        return isset($GLOBALS['_mysql_error']) ? $GLOBALS['_mysql_error'] : '';
    }

    function mysql_close($link = null) {
        if ($link) {
            $link = null;
            return true;
        }
        $GLOBALS['mylink'] = null;
        return true;
    }
}
?>
