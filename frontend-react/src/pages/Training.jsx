// eslint-disable-next-line no-unused-vars
import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import api from "../api/client";
import { getApiErrorMessage } from "../utils/errors";
import { useSession } from "../context/SessionContext";
import PageHeader from "../components/ui/PageHeader";
import {
  EmptyState,
  FeedbackMessage,
  LoadingState,
} from "../components/ui/StatePanel";
import {
  TrainingCourseOverview,
  TrainingCourseSidebar,
  TrainingQualityPanel,
} from "../features/training/TrainingAdminPanels";
import { TrainingPreviewModal } from "../features/training/TrainingModals";
import TrainingAdminQuiz from "../features/training/TrainingAdminQuiz";
import TrainingAssignmentsPanel from "../features/training/TrainingAssignmentsPanel";
import TrainingContentEditor from "../features/training/TrainingContentEditor";
import TrainingEmployeeJourney from "../features/training/TrainingEmployeeJourney";
import { recommendedSession } from "../features/training/trainingUtils";


function Training() {
  const { principal, hasPermission } = useSession();
  const canManage = hasPermission("training.manage");
  const canAssign = hasPermission("training.assign");
  const canViewResults = hasPermission("training.results.read");
  const canTakeQuiz = hasPermission("training.quiz.take");
  const firstName = principal?.profile?.first_name || "equipo";

  const [myAssignments, setMyAssignments] = useState([]);
  const [courses, setCourses] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [selectedCourse, setSelectedCourse] = useState(null);
  const [courseAssignments, setCourseAssignments] = useState([]);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState("");
  const [employeeCourse, setEmployeeCourse] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadingLessonId, setUploadingLessonId] = useState("");
  const [moduleForm, setModuleForm] = useState({
    title: "",
    description: "",
    audience_job_title: "",
    audience_department: "",
  });
  const [lessonForms, setLessonForms] = useState({});
  const [assignEmployeeId, setAssignEmployeeId] = useState("");
  const [quizForm, setQuizForm] = useState({
    title: "Evaluación final",
    passing_score: "70",
  });
  const [questionForm, setQuestionForm] = useState({
    prompt: "",
    options: ["", "", "", ""],
    correct_option: "0",
  });
  const [employeeQuiz, setEmployeeQuiz] = useState(null);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [activeLessonId, setActiveLessonId] = useState("");
  const [checklistSavingLessonId, setChecklistSavingLessonId] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewEmployeeId, setPreviewEmployeeId] = useState("");
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const loadHome = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const requests = [api.get("/training/me")];
      if (canManage) requests.push(api.get("/training/courses"));
      if (canAssign) requests.push(api.get("/employees"));

      const responses = await Promise.all(requests);
      const myItems = Array.isArray(responses[0]?.data?.items)
        ? responses[0].data.items
        : [];
      setMyAssignments(myItems);

      let index = 1;
      if (canManage) {
        const managedItems = Array.isArray(responses[index]?.data?.items)
          ? responses[index].data.items
          : [];
        setCourses(managedItems);
        setSelectedCourseId((current) => {
          if (current && managedItems.some((item) => item.id === current)) return current;
          return managedItems[0]?.id || "";
        });
        index += 1;
      }
      if (canAssign) {
        const employeeItems = Array.isArray(responses[index]?.data?.items)
          ? responses[index].data.items
          : [];
        setEmployees(employeeItems);
      }

      setSelectedAssignmentId((current) => {
        if (current && myItems.some((item) => item.id === current)) return current;
        return myItems[0]?.id || "";
      });
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar la capacitación",
        resource: "cursos y asignaciones",
        fallback: "No se pudo completar la vista de capacitación. Recarga la página para consultar nuevamente cursos, asignaciones y progreso.",
      }));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [canAssign, canManage]);

  const loadAdminCourse = useCallback(async (courseId) => {
    if (!canManage || !courseId) {
      setSelectedCourse(null);
      setCourseAssignments([]);
      return;
    }
    setDetailLoading(true);
    try {
      const requests = [api.get(`/training/courses/${courseId}`)];
      if (canViewResults) {
        requests.push(api.get(`/training/courses/${courseId}/assignments`));
      }
      const [courseResponse, assignmentsResponse] = await Promise.all(requests);
      setSelectedCourse(courseResponse.data);
      setCourseAssignments(
        canViewResults && Array.isArray(assignmentsResponse?.data?.items)
          ? assignmentsResponse.data.items
          : [],
      );
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "cargar el curso",
        resource: "contenido de capacitación",
        fallback: "El catálogo cargó, pero este curso no. Vuelve al listado y ábrelo nuevamente para confirmar que siga disponible.",
      }));
    } finally {
      setDetailLoading(false);
    }
  }, [canManage, canViewResults]);

  const selectedAssignment = useMemo(
    () => myAssignments.find((assignment) => assignment.id === selectedAssignmentId),
    [myAssignments, selectedAssignmentId],
  );

  const journeyLessons = useMemo(
    () => (
      employeeCourse?.course?.modules || []
    ).flatMap((module) => (
      module.lessons || []
    ).map((lesson) => ({ ...lesson, module }))),
    [employeeCourse],
  );

  const activeJourneyLesson = useMemo(
    () => journeyLessons.find((lesson) => lesson.id === activeLessonId) || null,
    [activeLessonId, journeyLessons],
  );

  const activeJourneyIndex = useMemo(
    () => journeyLessons.findIndex((lesson) => lesson.id === activeLessonId),
    [activeLessonId, journeyLessons],
  );

  const previousJourneyLesson = activeJourneyIndex > 0
    ? journeyLessons[activeJourneyIndex - 1]
    : null;
  const nextRequiredJourneyLesson = useMemo(
    () => journeyLessons.find(
      (lesson) => lesson.id === employeeCourse?.course?.next_lesson_id,
    ) || null,
    [employeeCourse?.course?.next_lesson_id, journeyLessons],
  );

  const currentRecommendedSession = useMemo(
    () => recommendedSession(
      journeyLessons,
      employeeCourse?.course?.next_lesson_id,
    ),
    [employeeCourse?.course?.next_lesson_id, journeyLessons],
  );

  function openFinalQuiz() {
    document.getElementById("training-final-quiz")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  const loadEmployeeCourse = useCallback(async (courseId, { silent = false } = {}) => {
    if (!courseId) {
      setEmployeeCourse(null);
      setEmployeeQuiz(null);
      return;
    }
    if (!silent) setDetailLoading(true);
    try {
      const { data } = await api.get(`/training/me/courses/${courseId}`);
      setEmployeeCourse(data);
      setActiveLessonId((current) => (
        current && (data.course?.modules || []).some((module) => (
          (module.lessons || []).some((lesson) => lesson.id === current)
        ))
          ? current
          : data.course?.next_lesson_id
            || data.course?.modules?.[0]?.lessons?.[0]?.id
            || ""
      ));
      setQuizResult(null);
      setQuizAnswers({});

      const lessonsComplete = (
        data.course?.lesson_count > 0
        && data.course?.completed_lessons >= data.course?.lesson_count
      );
      if (canTakeQuiz && data.course?.has_quiz && lessonsComplete) {
        const quizResponse = await api.get(`/training/me/courses/${courseId}/quiz`);
        setEmployeeQuiz(quizResponse.data);
      } else {
        setEmployeeQuiz(null);
      }
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "abrir tu curso asignado",
        resource: "capacitación asignada",
        fallback: "El curso está asignado, pero su contenido no se pudo abrir. Recarga la capacitación antes de continuar.",
      }));
    } finally {
      if (!silent) setDetailLoading(false);
    }
  }, [canTakeQuiz]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadHome();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadHome]);

  useEffect(() => {
    if (!selectedCourseId) return undefined;
    const timeoutId = window.setTimeout(() => {
      void loadAdminCourse(selectedCourseId);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadAdminCourse, selectedCourseId]);

  useEffect(() => {
    const courseId = selectedAssignment?.course?.id;
    if (!courseId) return undefined;
    const timeoutId = window.setTimeout(() => {
      void loadEmployeeCourse(courseId);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadEmployeeCourse, selectedAssignment]);

  async function loadCoursePreview(employeeId = "") {
    if (!selectedCourseId) return;
    setPreviewLoading(true);
    setError("");
    try {
      const config = employeeId
        ? { params: { employee_id: employeeId } }
        : undefined;
      const { data } = await api.get(
        `/training/courses/${selectedCourseId}/preview`,
        config,
      );
      setPreviewData(data);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "generar la vista previa del contenido",
        resource: "contenido de capacitación",
        fallback: "No se generó una vista previa temporal. El contenido original no cambió; vuelve a intentarlo desde la lección.",
      }));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function openCoursePreview() {
    setPreviewOpen(true);
    setPreviewEmployeeId("");
    setPreviewData(null);
    await loadCoursePreview("");
  }

  async function changePreviewEmployee(employeeId) {
    setPreviewEmployeeId(employeeId);
    await loadCoursePreview(employeeId);
  }

  function closeCoursePreview() {
    if (previewLoading) return;
    setPreviewOpen(false);
    setPreviewEmployeeId("");
    setPreviewData(null);
  }

  async function publishCourse() {
    if (!selectedCourseId) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put(`/training/courses/${selectedCourseId}`, {
        status: "PUBLISHED",
      });
      setSelectedCourse(data);
      await loadHome();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "publicar el curso",
        resource: "capacitación",
        fallback: "El curso conserva su estado anterior y no quedó publicado. Revisa que tenga contenido válido antes de volver a publicarlo.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function updateCourse(payload) {
    if (!selectedCourseId) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put(
        `/training/courses/${selectedCourseId}`,
        payload,
      );
      setSelectedCourse(data);
      await loadHome();
      return data;
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar el curso",
        resource: "capacitación",
        fallback: "El curso conserva su información anterior. Revisa el nombre y la descripción antes de volver a guardar.",
      }));
      throw err;
    } finally {
      setSaving(false);
    }
  }

  async function addModule(event) {
    event.preventDefault();
    if (!selectedCourseId) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(
        `/training/courses/${selectedCourseId}/modules`,
        {
          title: moduleForm.title.trim(),
          description: moduleForm.description.trim() || null,
          audience_job_title: moduleForm.audience_job_title.trim() || null,
          audience_department: moduleForm.audience_department.trim() || null,
        },
      );
      setSelectedCourse(data);
      setModuleForm({
        title: "",
        description: "",
        audience_job_title: "",
        audience_department: "",
      });
      await loadHome();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "agregar el módulo",
        resource: "curso",
        fallback: "El módulo no se agregó al curso. Revisa su título y vuelve a guardar la estructura.",
      }));
    } finally {
      setSaving(false);
    }
  }

  function lessonForm(moduleId) {
    return lessonForms[moduleId] || {
      title: "",
      description: "",
      video_url: "",
      duration_seconds: "",
      content_type: "VIDEO",
      external_url: "",
      estimated_minutes: "",
      checklist_items: "",
      is_optional: false,
    };
  }

  function updateLessonForm(moduleId, patch) {
    setLessonForms((current) => ({
      ...current,
      [moduleId]: {
        ...(current[moduleId] || {
          title: "",
          description: "",
          video_url: "",
          duration_seconds: "",
          content_type: "VIDEO",
          external_url: "",
          estimated_minutes: "",
          is_optional: false,
        }),
        ...patch,
      },
    }));
  }

  async function addLesson(event, moduleId) {
    event.preventDefault();
    const form = lessonForm(moduleId);
    setSaving(true);
    setError("");
    try {
      const duration = form.duration_seconds
        ? Number.parseInt(form.duration_seconds, 10)
        : null;
      const estimatedMinutes = form.estimated_minutes
        ? Number.parseInt(form.estimated_minutes, 10)
        : null;
      const { data } = await api.post(`/training/modules/${moduleId}/lessons`, {
        title: form.title.trim(),
        description: form.description.trim() || null,
        video_url: form.video_url.trim() || null,
        duration_seconds: Number.isInteger(duration) ? duration : null,
        content_type: form.content_type,
        external_url: form.external_url.trim() || null,
        estimated_minutes: Number.isInteger(estimatedMinutes) ? estimatedMinutes : null,
        checklist_items: form.content_type === "CHECKLIST"
          ? form.checklist_items
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean)
          : [],
        is_optional: Boolean(form.is_optional),
      });
      setSelectedCourse(data);
      setLessonForms((current) => ({
        ...current,
        [moduleId]: {
          title: "",
          description: "",
          video_url: "",
          duration_seconds: "",
          content_type: "VIDEO",
          external_url: "",
          estimated_minutes: "",
          is_optional: false,
        },
      }));
      await loadHome();
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "agregar la lección",
        resource: "módulo",
        fallback: "La lección no se creó. Revisa el tipo de contenido y los campos obligatorios antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function updateModule(moduleId, payload) {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put(`/training/modules/${moduleId}`, payload);
      setSelectedCourse(data);
      await loadHome();
      return data;
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar el módulo",
        resource: "onboarding",
        fallback: "El módulo conserva su contenido anterior. Revisa los campos y vuelve a guardar.",
      }));
      throw err;
    } finally {
      setSaving(false);
    }
  }

  async function updateLesson(lessonId, payload) {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.put(`/training/lessons/${lessonId}`, payload);
      setSelectedCourse(data);
      await loadHome();
      return data;
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "actualizar la lección",
        resource: "onboarding",
        fallback: "La lección conserva su contenido anterior. Revisa los campos y vuelve a guardar.",
      }));
      throw err;
    } finally {
      setSaving(false);
    }
  }

  async function uploadLessonVideo(lessonId, file) {
    if (!file) return;
    const allowedTypes = ["video/mp4", "video/webm", "video/ogg"];
    if (!allowedTypes.includes(file.type)) {
      setError("Formato no soportado. Usa MP4, WebM u OGG.");
      return;
    }
    if (file.size <= 0 || file.size > 1024 * 1024 * 1024) {
      setError("El video debe pesar como máximo 1 GB.");
      return;
    }

    setUploadingLessonId(lessonId);
    setError("");
    try {
      const manifest = {
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      };
      const { data } = await api.post(
        `/training/lessons/${lessonId}/video/upload`,
        manifest,
      );

      const formData = new FormData();
      Object.entries(data.upload.fields || {}).forEach(([key, value]) => {
        formData.append(key, value);
      });
      formData.append("file", file);

      const uploadResponse = await fetch(data.upload.url, {
        method: "POST",
        body: formData,
      });
      if (!uploadResponse.ok) {
        throw new Error("S3 upload failed");
      }

      const finalized = await api.post(
        `/training/lessons/${lessonId}/video/complete`,
        {
          key: data.key,
          content_type: file.type,
          size_bytes: file.size,
        },
      );
      setSelectedCourse(finalized.data);
      await loadHome();
    } catch (err) {
      setError(
        err.response?.data?.detail
          || getApiErrorMessage(err, {
            action: "subir el video",
            resource: "lección",
            fallback: "El video no quedó asociado a la lección. Conserva el archivo local y vuelve a iniciar la carga.",
          }),
      );
    } finally {
      setUploadingLessonId("");
    }
  }

  async function assignCourse(event) {
    event.preventDefault();
    if (!selectedCourseId || !assignEmployeeId) return;
    setSaving(true);
    setError("");
    try {
      await api.post(
        `/training/courses/${selectedCourseId}/assignments/${assignEmployeeId}`,
      );
      setAssignEmployeeId("");
      await loadAdminCourse(selectedCourseId);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "asignar el curso al empleado",
        resource: "asignación de capacitación",
        fallback: "El curso no quedó asignado. Actualiza la lista de empleados y confirma que el perfil siga activo.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function completeLesson(lessonId) {
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(
        `/training/me/lessons/${lessonId}/complete`,
      );
      setEmployeeCourse(data);
      await Promise.all([
        loadHome({ silent: true }),
        loadEmployeeCourse(data.course.id, { silent: true }),
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "guardar el avance de la lección",
        resource: "tu progreso",
        fallback: "Este avance no quedó registrado. Mantén la lección abierta y vuelve a marcarla cuando haya conexión.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function updateChecklistItem(lesson, index, checked) {
    if (!lesson?.id) return;
    const current = new Set(lesson.checklist_completed_items || []);
    if (checked) current.add(index);
    else current.delete(index);
    const completedItems = Array.from(current).sort((a, b) => a - b);
    const willComplete = completedItems.length === (lesson.checklist_items || []).length;
    const currentIndex = journeyLessons.findIndex((item) => item.id === lesson.id);
    const nextId = currentIndex >= 0
      ? journeyLessons[currentIndex + 1]?.id || ""
      : "";

    setChecklistSavingLessonId(lesson.id);
    setError("");
    try {
      const { data } = await api.put(
        `/training/me/lessons/${lesson.id}/checklist`,
        { completed_items: completedItems },
      );
      setEmployeeCourse(data);
      await Promise.all([
        loadHome({ silent: true }),
        loadEmployeeCourse(data.course.id, { silent: true }),
      ]);
      if (willComplete && nextId) setActiveLessonId(nextId);
    } catch (err) {
      setError(
        getApiErrorMessage(err, {
        action: "guardar el checklist",
        resource: "tu progreso",
        fallback: "Los cambios del checklist no quedaron confirmados. Revisa nuevamente los ítems antes de continuar.",
      }),
      );
    } finally {
      setChecklistSavingLessonId("");
    }
  }

  async function createQuiz(event) {
    event.preventDefault();
    if (!selectedCourseId) return;
    setSaving(true);
    setError("");
    try {
      await api.post(`/training/courses/${selectedCourseId}/quiz`, {
        title: quizForm.title.trim(),
        passing_score: Number.parseInt(quizForm.passing_score, 10),
      });
      await loadAdminCourse(selectedCourseId);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "crear la evaluación",
        resource: "curso",
        fallback: "La evaluación no se creó. Revisa el puntaje mínimo y la configuración del curso antes de reintentar.",
      }));
    } finally {
      setSaving(false);
    }
  }

  function updateQuestionOption(index, value) {
    setQuestionForm((current) => ({
      ...current,
      options: current.options.map((option, optionIndex) => (
        optionIndex === index ? value : option
      )),
    }));
  }

  async function addQuizQuestion(event) {
    event.preventDefault();
    const quizId = selectedCourse?.quiz?.id;
    if (!quizId) return;
    setSaving(true);
    setError("");
    try {
      await api.post(`/training/quizzes/${quizId}/questions`, {
        prompt: questionForm.prompt.trim(),
        options: questionForm.options.map((option) => option.trim()),
        correct_option: Number.parseInt(questionForm.correct_option, 10),
      });
      setQuestionForm({
        prompt: "",
        options: ["", "", "", ""],
        correct_option: "0",
      });
      await loadAdminCourse(selectedCourseId);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "agregar la pregunta",
        resource: "evaluación",
        fallback: "La pregunta no se guardó. Revisa enunciado, opciones y respuesta correcta antes de volver a enviarla.",
      }));
    } finally {
      setSaving(false);
    }
  }

  async function submitQuiz(event) {
    event.preventDefault();
    const courseId = employeeCourse?.course?.id;
    if (!courseId || !employeeQuiz) return;
    setSaving(true);
    setError("");
    try {
      const { data } = await api.post(
        `/training/me/courses/${courseId}/quiz/attempts`,
        { answers: quizAnswers },
      );
      setQuizResult(data);
      await Promise.all([
        loadHome(),
        loadEmployeeCourse(courseId),
      ]);
      setQuizResult(data);
    } catch (err) {
      setError(getApiErrorMessage(err, {
        action: "enviar la evaluación",
        resource: "evaluación",
        fallback: "El intento no quedó registrado. No cierres el curso hasta volver a enviar tus respuestas.",
      }));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <LoadingState label="Preparando capacitación…" />
      </div>
    );
  }

  return (
    <div className="page training-page">
      <PageHeader
        eyebrow="Aprendizaje interno"
        title="Capacitación"
        description={canManage
          ? `Hola, ${firstName}. El Onboarding ASIATI se asigna automáticamente; aquí revisas progreso y resultados.`
          : `Hola, ${firstName}. Cursos, videos y progreso en un solo lugar.`}
        className="split-header"
      />

      {error && <FeedbackMessage title="La capacitación no pudo completar la operación">{error}</FeedbackMessage>}

      {canManage && (
        <section className={`training-admin-layout ${courses.length === 1 ? "is-single-course" : ""}`}>
          {courses.length > 1 && (
            <TrainingCourseSidebar
              courses={courses}
              selectedCourseId={selectedCourseId}
              onSelectCourse={setSelectedCourseId}
            />
          )}

          <div className="training-admin-content">
            {detailLoading && !selectedCourse ? (
              <section className="panel"><LoadingState label="Cargando curso…" compact /></section>
            ) : selectedCourse ? (
              <>
                <div className="training-admin-summary-grid">
                  <TrainingCourseOverview
                    course={selectedCourse}
                    saving={saving}
                    onPreview={openCoursePreview}
                    onPublish={publishCourse}
                    onUpdateCourse={updateCourse}
                  />

                  <TrainingQualityPanel quality={selectedCourse.quality} />
                </div>

                <TrainingContentEditor
                  course={selectedCourse}
                  moduleForm={moduleForm}
                  onModuleFormChange={(patch) => setModuleForm((current) => ({ ...current, ...patch }))}
                  lessonForm={lessonForm}
                  onLessonFormChange={updateLessonForm}
                  onAddModule={addModule}
                  onAddLesson={addLesson}
                  onUpdateModule={updateModule}
                  onUpdateLesson={updateLesson}
                  onUploadLessonVideo={uploadLessonVideo}
                  uploadingLessonId={uploadingLessonId}
                  saving={saving}
                />

                <TrainingAdminQuiz
                  course={selectedCourse}
                  quizForm={quizForm}
                  onQuizFormChange={(patch) => setQuizForm((current) => ({ ...current, ...patch }))}
                  onCreateQuiz={createQuiz}
                  questionForm={questionForm}
                  onQuestionFormChange={(patch) => setQuestionForm((current) => ({ ...current, ...patch }))}
                  onQuestionOptionChange={updateQuestionOption}
                  onAddQuestion={addQuizQuestion}
                  saving={saving}
                />

                {(canAssign || canViewResults) && (
                  <TrainingAssignmentsPanel
                    course={selectedCourse}
                    employees={employees}
                    employeeId={assignEmployeeId}
                    onEmployeeChange={setAssignEmployeeId}
                    onAssignCourse={assignCourse}
                    saving={saving}
                    canAssign={canAssign}
                    canViewResults={canViewResults}
                    assignments={courseAssignments}
                  />
                )}
              </>
            ) : (
              <section className="panel">
                <EmptyState
                  compact
                  icon="training"
                  title="Selecciona una ruta"
                  description="Los contenidos y asignaciones del onboarding se provisionan automáticamente; desde aquí revisas progreso y resultados."
                />
              </section>
            )}
          </div>
        </section>
      )}

      <TrainingEmployeeJourney
        canManage={canManage}
        myAssignments={myAssignments}
        selectedAssignmentId={selectedAssignmentId}
        setSelectedAssignmentId={setSelectedAssignmentId}
        detailLoading={detailLoading}
        employeeCourse={employeeCourse}
        currentRecommendedSession={currentRecommendedSession}
        selectedAssignment={selectedAssignment}
        setActiveLessonId={setActiveLessonId}
        activeLessonId={activeLessonId}
        activeJourneyLesson={activeJourneyLesson}
        checklistSavingLessonId={checklistSavingLessonId}
        updateChecklistItem={updateChecklistItem}
        previousJourneyLesson={previousJourneyLesson}
        completeLesson={completeLesson}
        saving={saving}
        nextRequiredJourneyLesson={nextRequiredJourneyLesson}
        openFinalQuiz={openFinalQuiz}
        employeeQuiz={employeeQuiz}
        quizAnswers={quizAnswers}
        setQuizAnswers={setQuizAnswers}
        quizResult={quizResult}
        submitQuiz={submitQuiz}
      />

      <TrainingPreviewModal
        open={previewOpen}
        onClose={closeCoursePreview}
        loading={previewLoading}
        employees={employees}
        employeeId={previewEmployeeId}
        onChangeEmployee={changePreviewEmployee}
        data={previewData}
      />

    </div>
  );
}

export default Training;
