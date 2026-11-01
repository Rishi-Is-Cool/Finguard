// src/components/FileUpload.jsx
import { useState, useRef } from 'react'
import { Upload, FileText } from 'lucide-react'
import { API } from '../hooks/useFinGuard.js'

export function FileUpload({ onUpload, isUploading, uploadInfo }) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef(null)

  const handleFile = (file) => {
    if (!file) return
    if (!file.name.endsWith('.csv')) {
      alert('Please upload a CSV file.')
      return
    }
    onUpload(file)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  if (uploadInfo) {
    return (
      <div className="bg-green-900/30 border border-green-500/40 rounded-xl p-5 flex items-center gap-4">
        <div className="bg-green-500/20 p-3 rounded-lg">
          <FileText className="text-green-400" size={24} />
        </div>
        <div>
          <p className="font-medium text-green-300">{uploadInfo.filename}</p>
          <p className="text-sm text-slate-400 mt-0.5">
            {uploadInfo.row_count.toLocaleString()} transactions · ID: {uploadInfo.document_id}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all
        ${isDragging
          ? 'border-blue-400 bg-blue-900/20'
          : 'border-slate-600 hover:border-slate-400 bg-slate-800/30'}`}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => handleFile(e.target.files[0])}
      />

      {isUploading ? (
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-slate-400">Uploading...</p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="bg-slate-700/50 p-4 rounded-full">
            <Upload className="text-slate-400" size={28} />
          </div>
          <div>
            <p className="font-medium text-slate-300">Drop your CSV here or click to browse</p>
            <p className="text-sm text-slate-500 mt-1">
              Columns: date, time, account, beneficiary, description, amount, type
            </p>
          </div>
          <a
            href={`${API}/sample.csv`}
            onClick={e => e.stopPropagation()}
            className="text-xs text-blue-400 hover:text-blue-300 underline underline-offset-2"
          >
            Download the sample CSV to see the format
          </a>
        </div>
      )}
    </div>
  )
}
