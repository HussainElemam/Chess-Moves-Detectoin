package com.example.chess_moves_tracking

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import org.opencv.core.*
import org.opencv.imgcodecs.Imgcodecs
import org.opencv.imgproc.Imgproc
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.nnapi.NnApiDelegate
import org.tensorflow.lite.DataType
import java.io.File
import java.io.FileInputStream
import java.io.FileWriter
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel
import java.text.SimpleDateFormat
import java.util.*
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

class BoardEngine(
    private val ctx: Context,
    private val modelAsset: String,
    private val warpSize: Int = 512,      // Changed from 640 to 512 for speed
    private val insetFrac: Double = 0.08,
    private val expandFrac: Double = 0.50, // NEW: expand to include surrounding space
    private val gridSize: Int = 10,        // NEW: 10x10 grid (8x8 playing + 1 border)
    private val playingSize: Int = 8,      // NEW: actual playing area
    private val minStableFrames: Int = 2,
    private val downscaleMax: Int = 640    // Changed from 960 to 640
) {
    private val labels = loadLabels(ctx)
    private val delegate = NnApiDelegate()
    private lateinit var tflite: Interpreter
    private lateinit var io: TfIO
    private var inH: Int = 0
    private var inW: Int = 0

    private var frameCount = 0
    private var prevFen: String? = null
    private var candidate: String? = null
    private var stable = 0
    private var sampleCounter = 0
    private val sampleDir by lazy { File(ctx.getExternalFilesDir(null), "chess_samples").apply { mkdirs() } }
    
    // Logging
    private var gameId: String? = null
    private val logEntries = mutableListOf<LogEntry>()
    private val logDir by lazy { File(ctx.getExternalFilesDir(null), "chess_logs").apply { mkdirs() } }
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    
    data class LogEntry(
        val timestamp: String,
        val frameNumber: Int,
        val gameId: String?,
        val labels64: List<String>,
        val fen: String,
        val candidate: String?,
        val stable: Int,
        val isStableChange: Boolean,
        val imageFile: String? = null  // Path to saved frame image
    )

    init {
        val (interpreter, tfInfo) = makeInterpreter(ctx, "pieces_int8.tflite")
        tflite = interpreter
        io = tfInfo
        val s = tflite.getInputTensor(0).shape() // [1,h,w,3]
        inH = if (s.size == 4) s[1] else s[0]
        inW = if (s.size == 4) s[2] else s[1]
    }

    data class TfIO(
        val inType: DataType, val inScale: Float, val inZero: Int,
        val outType: DataType, val outScale: Float, val outZero: Int
    )

    private fun tfInfo(tflite: Interpreter): TfIO {
        val inT  = tflite.getInputTensor(0)
        val outT = tflite.getOutputTensor(0)
        val inQ  = inT.quantizationParams()
        val outQ = outT.quantizationParams()
        return TfIO(
            inT.dataType(),  (inQ.scale  ?: 0f), (inQ.zeroPoint  ?: 0),
            outT.dataType(), (outQ.scale ?: 0f), (outQ.zeroPoint ?: 0)
        )
    }

    private fun makeInterpreter(ctx: Context, asset: String): Pair<Interpreter, TfIO> {
        val fd = ctx.assets.openFd(asset)
        val mapped = FileInputStream(fd.fileDescriptor).channel
            .map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
        val opts = Interpreter.Options().apply {
            setNumThreads(3)
            // Prefer XNNPACK; NNAPI can be used too, but XNNPACK is great on CPU.
            // addDelegate(NnApiDelegate())   // optional: try on devices with NNAPI edge
        }
        val interp = Interpreter(mapped, opts)
        return interp to tfInfo(interp)
    }

    fun close() {
        tflite.close()
        delegate.close()
    }

    // Public: returns FEN when a *stable* change is detected; otherwise null
    fun processYuvAndGetFen(
        width: Int, height: Int,
        y: ByteArray, u: ByteArray, v: ByteArray,
        strideY: Int, strideU: Int, strideV: Int,
        pxU: Int, pxV: Int,
        processEvery: Int = 3
    ): String? {
        frameCount++
        if (frameCount % processEvery != 0) return null

        val nv21 = yuv420ToNV21(width, height, y,u,v, strideY,strideU,strideV, pxU,pxV)
        val yuv = Mat(height + height/2, width, CvType.CV_8UC1)
        yuv.put(0, 0, nv21)

        val bgr = Mat()
        Imgproc.cvtColor(yuv, bgr, Imgproc.COLOR_YUV2BGR_NV21)
        yuv.release()
        val scaled = resizeMax(bgr, downscaleMax)
        bgr.release()

        // Debug: save scaled image every 100 frames to check if input is OK
        sampleCounter++
        if (sampleCounter % 100 == 0) {
            try {
                val scaledFile = File(sampleDir, "scaled_${sampleCounter}.png")
                Imgcodecs.imwrite(scaledFile.absolutePath, scaled)
            } catch (e: Exception) {
                // Silent fail
            }
        }

        val quad = detectQuad(scaled) ?: run { scaled.release(); return null }
        val warp = warpFromQuad(scaled, quad, warpSize)
        scaled.release()
        ensureTopLeftDark(warp)

        // Actual model detection
        val labels64 = classify64(warp)
        val fen = toFen(labels64)

        // Stability check: only return when stable position is detected
        val isStableChange: Boolean
        if (prevFen == null) {
            prevFen = fen
            candidate = fen; stable = 1
            isStableChange = true
        } else {
            if (candidate == fen) {
                stable++
            } else {
                candidate = fen
                stable = 1
            }
            // Return only when we have a stable change (minStableFrames reached)
            isStableChange = if (stable >= minStableFrames && prevFen != candidate) {
                prevFen = candidate
                true
            } else {
                false
            }
        }

        // Log this prediction with the warped board image
        logPrediction(labels64, fen, candidate, stable, isStableChange, warp)
        warp.release()

        return if (isStableChange) {
            prevFen
        } else null
    }

    // ---- helpers ----

    private fun loadLabels(ctx: Context, fname: String = "label_map.txt"): Array<String> {
        val out = mutableListOf<String>()
        ctx.assets.open(fname).bufferedReader().useLines { lines ->
            lines.forEach { val s = it.trim(); if (s.isNotEmpty()) out.add(s) }
        }
        return out.toTypedArray()
    }

    private fun resizeMax(src: Mat, maxSide: Int): Mat {
        val h = src.rows(); val w = src.cols(); val s = max(h, w)
        if (s <= maxSide) return src.clone()
        val scale = maxSide.toDouble() / s
        val dst = Mat()
        Imgproc.resize(src, dst, Size(w*scale, h*scale), 0.0, 0.0, Imgproc.INTER_AREA)
        return dst
    }

    private fun detectQuad(bgr: Mat): MatOfPoint2f? {
        val gray = Mat()
        Imgproc.cvtColor(bgr, gray, Imgproc.COLOR_BGR2GRAY)

        // Threshold to separate white background from board
        val thresh = Mat()
        Imgproc.threshold(gray, thresh, 0.0, 255.0, Imgproc.THRESH_BINARY_INV + Imgproc.THRESH_OTSU)

        // Fallback if Otsu doesn't capture enough
        val threshArea = Core.countNonZero(thresh)
        if (threshArea < 0.05 * thresh.rows() * thresh.cols()) {
            Imgproc.threshold(gray, thresh, 200.0, 255.0, Imgproc.THRESH_BINARY_INV)
        }

        // Morphological cleanup: close then open
        val kernel = Imgproc.getStructuringElement(Imgproc.MORPH_RECT, Size(5.0, 5.0))
        for (i in 0 until 2) Imgproc.morphologyEx(thresh, thresh, Imgproc.MORPH_CLOSE, kernel)
        Imgproc.morphologyEx(thresh, thresh, Imgproc.MORPH_OPEN, kernel)

        // Find contours
        val contours = ArrayList<MatOfPoint>()
        Imgproc.findContours(thresh, contours, Mat(), Imgproc.RETR_EXTERNAL, Imgproc.CHAIN_APPROX_SIMPLE)
        thresh.release()
        gray.release()

        if (contours.isEmpty()) return null

        // Sort by area and find largest contour with area >= 5% of image
        contours.sortByDescending { Imgproc.contourArea(it) }
        val imgArea = bgr.rows().toDouble() * bgr.cols().toDouble()
        val minArea = 0.05 * imgArea

        var best: MatOfPoint2f? = null

        for (c in contours) {
            val area = Imgproc.contourArea(c)
            if (area < minArea) {
                c.release()
                continue
            }

            val p2f = MatOfPoint2f(*c.toArray())
            val peri = Imgproc.arcLength(p2f, true)
            val approx = MatOfPoint2f()
            
            // Try epsilon=0.02*perimeter first
            Imgproc.approxPolyDP(p2f, approx, 0.02 * peri, true)

            if (approx.total().toInt() == 4) {
                best = approx
                p2f.release()
                break
            }
            approx.release()

            // Fallback: try tighter approximation (epsilon=0.01*perimeter)
            Imgproc.approxPolyDP(p2f, approx, 0.01 * peri, true)
            if (approx.total().toInt() == 4) {
                best = approx
                p2f.release()
                break
            }
            approx.release()

            // Fallback: convex hull
            val hull = MatOfInt()
            val c_mat = MatOfPoint(*c.toArray())
            Imgproc.convexHull(c_mat, hull)
            c_mat.release()
            if (hull.total().toInt() == 4) {
                val hullPoints = hull.toArray().map { c.toArray()[it.toInt()] }.toTypedArray()
                best = MatOfPoint2f(*hullPoints)
                p2f.release()
                hull.release()
                break
            }
            hull.release()

            // Fallback: min area rect (skip for now as OpenCV RotatedRect.points() is complex)
            // Instead, just use the current contour's convex hull as fallback
            p2f.release()
        }

        contours.forEach { it.release() }
        return best?.let { orderQuad(it) }
    }

    private fun orderQuad(q: MatOfPoint2f): MatOfPoint2f {
        val pts = q.toArray()
        val sum = pts.map { it.x + it.y }
        val diff = pts.map { it.y - it.x }
        val tl = pts[sum.indexOf(sum.minOrNull()!!)]
        val br = pts[sum.indexOf(sum.maxOrNull()!!)]
        val tr = pts[diff.indexOf(diff.minOrNull()!!)]
        val bl = pts[diff.indexOf(diff.maxOrNull()!!)]
        q.release()
        return MatOfPoint2f(tl, tr, br, bl)
    }

    private fun warpFromQuad(bgr: Mat, quad: MatOfPoint2f, size: Int): Mat {
        val dst = MatOfPoint2f(
            Point(0.0, 0.0),
            Point((size-1).toDouble(), 0.0),
            Point((size-1).toDouble(), (size-1).toDouble()),
            Point(0.0, (size-1).toDouble())
        )
        val H = Imgproc.getPerspectiveTransform(quad, dst)
        val warped = Mat(size, size, bgr.type())
        Imgproc.warpPerspective(bgr, warped, H, Size(size.toDouble(), size.toDouble()), Imgproc.INTER_LINEAR)
        H.release(); dst.release(); quad.release()
        return warped
    }

    private fun ensureTopLeftDark(warpBgr: Mat) {
        val gray = Mat()
        Imgproc.cvtColor(warpBgr, gray, Imgproc.COLOR_BGR2GRAY)
        val h = gray.rows()
        val s = h / gridSize
        val inset = (s * insetFrac).toInt()

        // Score all 4 rotations based on checker pattern contrast in the playing area (8×8)
        val scores = DoubleArray(4) { rot ->
            var darkSum = 0.0
            var lightSum = 0.0
            var darkCount = 0
            var lightCount = 0

            // Check the 8×8 playing area (grid indices 1-8, skipping border)
            for (r in 0 until playingSize) {
                for (c in 0 until playingSize) {
                    val baseY0 = ((r + 1) * s + inset).toInt()
                    val baseY1 = ((r + 2) * s - inset).toInt()
                    val baseX0 = ((c + 1) * s + inset).toInt()
                    val baseX1 = ((c + 2) * s - inset).toInt()

                    val roi = gray.submat(baseY0, baseY1, baseX0, baseX1)
                    val m = Core.mean(roi).`val`[0]
                    roi.release()

                    // Checker pattern: (r+c) determines if dark or light
                    if (((r + c) and 1) == 0) {
                        darkSum += m
                        darkCount++
                    } else {
                        lightSum += m
                        lightCount++
                    }
                }
            }

            // Calculate contrast: |darkMean - lightMean|
            val darkMean = if (darkCount > 0) darkSum / darkCount else 0.0
            val lightMean = if (lightCount > 0) lightSum / lightCount else 0.0

            // For rotation 0, we want dark squares to be darker, so high contrast = dark > light is bad
            // We want lightMean > darkMean (light squares are lighter)
            when (rot) {
                0 -> (lightMean - darkMean) // Higher is better (positive if light > dark)
                1 -> (darkMean - lightMean) // 90° rotation: the parity flips
                2 -> (lightMean - darkMean) // 180° rotation: same as rotation 0
                else -> (darkMean - lightMean) // 270° rotation: same as rotation 1
            }
        }

        // Find rotation with best contrast score
        val bestRot = scores.withIndex().maxByOrNull { it.value }?.index ?: 0

        // Apply rotation(s) if needed (rotate by 90 degrees, bestRot times)
        if (bestRot > 0) {
            val temp = Mat()
            when (bestRot) {
                1 -> Core.rotate(warpBgr, temp, Core.ROTATE_90_CLOCKWISE)
                2 -> Core.rotate(warpBgr, temp, Core.ROTATE_180)
                3 -> Core.rotate(warpBgr, temp, Core.ROTATE_90_COUNTERCLOCKWISE)
                else -> warpBgr.copyTo(temp)
            }
            temp.copyTo(warpBgr)
            temp.release()
        }

        gray.release()
    }

    private fun classify64(warpBgr: Mat): List<String> {
        val H = warpBgr.rows()
        val S = H / gridSize  // Grid square size: warpBgr is 512×512, gridSize=10, so S=51.2
        val inset = (S * insetFrac).toInt()
        val expand = (S * expandFrac).toInt()
        val outLabels = ArrayList<String>(64)

        // Save sample board every 10 frames
        if (sampleCounter % 10 == 0) {
            try {
                val boardFile = File(sampleDir, "board_sample_${sampleCounter}.png")
                Imgcodecs.imwrite(boardFile.absolutePath, warpBgr)
            } catch (e: Exception) {
                // Silent fail for sampling
            }
        }

        // Pre-allocate buffers ONCE
        val floatIn = if (io.inType == DataType.FLOAT32)
            ByteBuffer.allocateDirect(4 * inH * inW * 3).order(ByteOrder.nativeOrder()) else null
        val int8In  = if (io.inType == DataType.INT8)
            ByteBuffer.allocateDirect(inH * inW * 3).order(ByteOrder.nativeOrder()) else null

        // Output buffers - model outputs shape [1, 13], so we need 2D arrays
        val floatOut = if (io.outType == DataType.FLOAT32) Array(1) { FloatArray(labels.size) } else null
        val int8Out  = if (io.outType == DataType.INT8)   Array(1) { ByteArray(labels.size) } else null

        // Temporary data buffer for reading pixel data
        val data = ByteArray(inH * inW * 3)

        // Extract 8×8 playing area from the 10×10 grid (skip border at r+1, c+1)
        for (r in 0 until playingSize) {
            for (c in 0 until playingSize) {
                // Base coordinates in the grid (grid positions 1-8, skipping border at 0 and 9)
                val baseY0 = ((r + 1) * S + inset).toInt()
                val baseY1 = ((r + 2) * S - inset).toInt()
                val baseX0 = ((c + 1) * S + inset).toInt()
                val baseX1 = ((c + 2) * S - inset).toInt()

                // Expand into surrounding squares
                val y0 = maxOf(0, baseY0 - expand)
                val y1 = minOf(H, baseY1 + expand)
                val x0 = maxOf(0, baseX0 - expand)
                val x1 = minOf(H, baseX1 + expand)

                val roi = warpBgr.submat(y0, y1, x0, x1)

                val rgb = Mat()
                Imgproc.cvtColor(roi, rgb, Imgproc.COLOR_BGR2RGB)
                val resized = Mat()
                Imgproc.resize(rgb, resized, Size(inW.toDouble(), inH.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
                rgb.release()
                roi.release()

                // Save sample pieces every 10 frames (just a few squares)
                if (sampleCounter % 10 == 0 && r < 2 && c < 2) {
                    try {
                        val pieceFile = File(sampleDir, "piece_${r}_${c}_sample_${sampleCounter}.png")
                        Imgcodecs.imwrite(pieceFile.absolutePath, resized)
                    } catch (e: Exception) {
                        // Silent fail for sampling
                    }
                }

                resized.get(0, 0, data)
                resized.release()

                when (io.inType) {
                    DataType.FLOAT32 -> {
                        floatIn!!.rewind()
                        // model expects [0,1] then internal Rescaling -> [-1,1]
                        val fb = floatIn.asFloatBuffer()
                        for (i in data.indices) {
                            fb.put((data[i].toInt() and 0xFF) / 255.0f)
                        }
                        if (io.outType == DataType.FLOAT32) {
                            tflite.run(floatIn, floatOut)
                            outLabels.add(labels[argmaxFloat(floatOut!![0])])
                        } else { // INT8 output
                            tflite.run(floatIn, int8Out)
                            outLabels.add(labels[argmaxInt8(int8Out!![0])])
                        }
                    }
                    DataType.INT8 -> {
                        int8In!!.rewind()
                        // Quantize from [0,1] float -> int8 using scale/zeroPoint
                        // v_q = round(v_f / scale + zeroPoint), clipped to [-128,127]
                        val s = if (io.inScale == 0f) 1f else io.inScale
                        val z = io.inZero
                        var i = 0
                        while (i < data.size) {
                            val v = (data[i].toInt() and 0xFF) / 255.0f
                            val q = (v / s + z).roundToInt().coerceIn(-128, 127)
                            int8In.put(q.toByte())
                            i++
                        }
                        if (io.outType == DataType.INT8) {
                            tflite.run(int8In, int8Out)
                            outLabels.add(labels[argmaxInt8(int8Out!![0])])
                        } else { // FLOAT32 output
                            tflite.run(int8In, floatOut)
                            outLabels.add(labels[argmaxFloat(floatOut!![0])])
                        }
                    }
                    else -> throw IllegalStateException("Unsupported input dtype: ${io.inType}")
                }
            }
        }
        return outLabels
    }

private fun argmaxFloat(arr: FloatArray): Int {
    var k = 0; var v = arr[0]
    for (i in 1 until arr.size) if (arr[i] > v) { v = arr[i]; k = i }
    return k
}
private fun argmaxInt8(arr: ByteArray): Int {
    var k = 0; var v = arr[0].toInt()
    for (i in 1 until arr.size) {
        val u = arr[i].toInt()
        if (u > v) { v = u; k = i }
    }
    return k
}

    private fun toFen(labels64: List<String>): String {
        val ranks = ArrayList<String>(8)
        for (r in 0 until 8) {
            var run = 0
            val sb = StringBuilder()
            for (c in 0 until 8) {
                val s = labels64[r*8 + c]
                if (s == ".") run++ else { if (run>0) { sb.append(run); run=0 }; sb.append(s) }
            }
            if (run>0) sb.append(run)
            ranks.add(sb.toString())
        }
        return ranks.joinToString("/") + " w - - 0 1"
    }

    private fun argmax(arr: FloatArray): Int {
        var k = 0; var v = arr[0]
        for (i in 1 until arr.size) if (arr[i] > v) { v = arr[i]; k = i }
        return k
    }

    private fun yuv420ToNV21(
        width: Int, height: Int,
        y: ByteArray, u: ByteArray, v: ByteArray,
        strideY: Int, strideU: Int, strideV: Int,
        pxU: Int, pxV: Int
    ): ByteArray {
        val ySize = width * height
        val uvSize = width * height / 2
        val out = ByteArray(ySize + uvSize)
        var src = 0; var dst = 0
        for (r in 0 until height) {
            System.arraycopy(y, src, out, dst, width)
            src += strideY; dst += width
        }
        var off = ySize
        for (r in 0 until height/2) {
            var uIdx = r * strideU
            var vIdx = r * strideV
            for (c in 0 until width/2) {
                out[off++] = v[vIdx]
                out[off++] = u[uIdx]
                vIdx += pxV; uIdx += pxU
            }
        }
        return out
    }

    private fun loadModel(asset: String): MappedByteBuffer {
        val fd = ctx.assets.openFd(asset)
        FileInputStream(fd.fileDescriptor).use { fis ->
            return fis.channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
        }
    }

    // ---- Logging methods ----

    fun setGameId(id: String?) {
        gameId = id
    }

    private fun logPrediction(
        labels64: List<String>,
        fen: String,
        candidate: String?,
        stable: Int,
        isStableChange: Boolean,
        warpImage: Mat? = null
    ) {
        val timestamp = dateFormat.format(Date())
        
        // Save frame image if provided
        var imageFile: String? = null
        if (warpImage != null) {
            try {
                imageFile = File(sampleDir, "frame_${frameCount}_${System.currentTimeMillis()}.png").absolutePath
                Imgcodecs.imwrite(imageFile, warpImage)
            } catch (e: Exception) {
                android.util.Log.w("BoardEngine", "Failed to save frame image: ${e.message}")
            }
        }
        
        val entry = LogEntry(
            timestamp = timestamp,
            frameNumber = frameCount,
            gameId = gameId,
            labels64 = labels64,
            fen = fen,
            candidate = candidate,
            stable = stable,
            isStableChange = isStableChange,
            imageFile = imageFile
        )
        logEntries.add(entry)
    }

    fun saveLogs(): String? {
        if (logEntries.isEmpty()) {
            return null
        }

        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val gameIdPart = if (gameId != null) "game_${gameId}_" else "predictions_"
        val logFile = File(logDir, "${gameIdPart}${timestamp}.log")

        try {
            FileWriter(logFile).use { writer ->
                writer.append("Chess Board Detection Log\n")
                writer.append("Game ID: ${gameId ?: "N/A"}\n")
                writer.append("Generated: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(Date())}\n")
                writer.append("Total Entries: ${logEntries.size}\n")
                writer.append("Sample Directory: ${sampleDir.absolutePath}\n")
                writer.append("=".repeat(100)).append("\n\n")

                logEntries.forEach { entry ->
                    writer.append("Timestamp: ${entry.timestamp}\n")
                    writer.append("Frame: ${entry.frameNumber}\n")
                    writer.append("Game ID: ${entry.gameId ?: "N/A"}\n")
                    writer.append("Labels (64 squares): ${entry.labels64.joinToString(",")}\n")
                    writer.append("FEN: ${entry.fen}\n")
                    writer.append("Candidate: ${entry.candidate ?: "N/A"}\n")
                    writer.append("Stable Count: ${entry.stable}\n")
                    writer.append("Stable Change: ${entry.isStableChange}\n")
                    if (entry.imageFile != null) {
                        writer.append("Frame Image: ${entry.imageFile}\n")
                    }
                    writer.append("-".repeat(100)).append("\n")
                }
            }
            android.util.Log.i("BoardEngine", "Logs saved to: ${logFile.absolutePath}")
            return logFile.absolutePath
        } catch (e: Exception) {
            android.util.Log.e("BoardEngine", "Error saving logs: ${e.message}", e)
            return null
        }
    }

    fun clearLogs() {
        logEntries.clear()
        gameId = null
    }
}
